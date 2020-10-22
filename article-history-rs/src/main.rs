use std::{
    collections::HashMap,
    error::Error,
};

use itertools::Itertools;
use mediawiki::{api::Api, page::Page, title::Title};
use parse_wiki_text::{Configuration, Node, Parameter};

mod common;
mod dyk;
mod itn;
mod otd;

const SUMMARY: &str = "[[Wikipedia:Bots/Requests for approval/APersonBot 7|Bot]] merging redundant talk page banners into [[Template:Article history]].";

// as of MW 1.35, the revision table has rev_id as a int(10) unsigned
type RevId = u32;

#[derive(Debug,Clone,Copy,PartialEq,Eq,Hash)]
enum TemplateType {
    ArticleHistory,
    Dyk,
    Itn,
    Otd,
}

#[derive(Debug)]
pub struct Template {
    name: TemplateType,
    unnamed: Vec<String>,
    named: linked_hash_map::LinkedHashMap<String, String>,
}

fn wikitext_to_template_list<'a>(wikitext: &'a str, page_name: &str, template_name_map: &HashMap<String, TemplateType>) -> Vec<Template> {
    let output = Configuration::default().parse(wikitext);
    assert!(
        output
            .warnings
            .iter()
            .filter(
                |warning| warning.message != parse_wiki_text::WarningMessage::UnrecognizedTagName
            )
            .next()
            .is_none(),
        "{:?}",
        output
    );
    output
        .nodes
        .into_iter()
        .filter_map(|node| match node {
            Node::Template {
                name: name_nodes,
                parameters,
                ..
            } => {
                let template_name = common::nodes_to_text(&name_nodes).unwrap_or_else(|e|
                    panic!(
                        "while handling '{}': nodes_to_text failed on template name: {}",
                        page_name, e
                    ));
                let template_type = if let Some(t) = template_name_map.get(template_name.as_ref()) {
                    *t
                } else {
                    return None;
                };
                let (named, unnamed): (Vec<_>, Vec<_>) = parameters
                    .iter()
                    .enumerate()
                    .map(|(param_idx, Parameter { name: name_nodes, value: value_nodes, .. })| {
                        let param_name = name_nodes.as_ref().map(|name_nodes| common::nodes_to_text(&name_nodes)
                            .unwrap_or_else(|e| panic!(
                                "while handling page '{}', template '{}': nodes_to_text failed on the name of parameter index {}: {}",
                                page_name, template_name, param_idx, e
                            )));
                        let param_value = common::nodes_to_text(&value_nodes)
                            .unwrap_or_else(|e| panic!(
                                "while handling page '{}', template '{}': nodes_to_text failed on the value for parameter '{:?}' (index {}): {}",
                                page_name, template_name, param_name, param_idx, e
                            ));
                        (param_name, param_value)
                    }).partition(|(name, _value)| name.is_some());
                let named = named.into_iter().map(|(name, value)| (name.unwrap().into_owned(), value.into_owned())).collect();
                let unnamed = unnamed.into_iter().map(|(_name, value)| value.into_owned()).collect();
                Some(Template {
                    name: template_type,
                    unnamed,
                    named,
                })
            },
            _ => None,
        })
        .collect()
}

fn make_map(params: &[(&str, &str)]) -> HashMap<String, String> {
    params.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
}

async fn build_template_name_map(api: &Api) -> HashMap<String, TemplateType> {
    let res = api.get_query_api_json_all(&make_map(&[
        ("action", "query"),
        ("titles", "Template:Article history|Template:DYK talk|Template:On this day|Template:ITN talk"),
        ("prop", "redirects"),
        ("formatversion", "2"),
    ])).await.expect("build_template_name_map");
    let mut map = HashMap::new();
    fn title_to_template_type(s: &str) -> TemplateType {
        match s {
            "Template:Article history" => TemplateType::ArticleHistory,
            "Template:DYK talk" => TemplateType::Dyk,
            "Template:On this day" => TemplateType::Otd,
            "Template:ITN talk" => TemplateType::Itn,
            _ => panic!("main.rs:{} {}", line!(), s),
        }
    }
    fn fix(s: &str) -> String {
        if s.get(..9) == Some("Template:") {
            &s[9..]
        } else {
            &s[..]
        }.to_string()
    }
    for page in res["query"]["pages"].as_array().unwrap() {
        let template_type = title_to_template_type(page["title"].as_str().unwrap());
        map.insert(fix(page["title"].as_str().unwrap()), template_type);
        for redirect in page["redirects"].as_array().unwrap_or(&vec![]) {
            map.insert(fix(redirect["title"].as_str().unwrap()), template_type);
        }
    }
    map
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let mut config = config::Config::default();
    config
        .merge(config::File::with_name("settings"))?
        .merge(config::Environment::with_prefix("APP"))?;
    let username = config.get_str("username")?;
    let password = config.get_str("password")?;

    let mut api = Api::new("https://en.wikipedia.org/w/api.php").await?;
    api.login(username, password).await?;
    api.set_user_agent(format!("EnterpriseyBot/article-history-rs/{} (https://en.wikipedia.org/wiki/User:EnterpriseyBot; apersonwiki@gmail.com)", env!("CARGO_PKG_VERSION")));

    let title = "Talk:FC Bayern Munich";
    let page = Page::new(Title::new_from_full(title, &api));
    let text = page.text(&api).await?;

    let text = if let Some(idx) = text.find("\n==") {
        &text[..idx]
    } else {
        &text[..]
    };

    let template_name_map = build_template_name_map(&api).await;
    let templates = wikitext_to_template_list(text, title, &template_name_map);
    let mut templates = templates
        .into_iter()
        .map(|template| (template.name, template))
        .into_group_map();

    // There ought to be only one article history
    assert!(templates[&TemplateType::ArticleHistory].len() == 1);

    let mut article_history = templates.remove(&TemplateType::ArticleHistory).unwrap().remove(0);
    for (template_type, templates) in templates.iter() {
        for template in templates {
            match template_type {
                TemplateType::Itn => common::update_article_history(itn::parse_itn_template(template), &mut article_history),
                TemplateType::Otd => common::update_article_history(otd::parse_otd_template(template), &mut article_history),
                TemplateType::Dyk => common::update_article_history(vec![dyk::parse_dyk_template(title, template).expect("dyk")], &mut article_history),
                TemplateType::ArticleHistory => unreachable!(),
            }
        }
    }
    println!("{:#?}", article_history);
    std::mem::drop(article_history);
    Ok(())
}
