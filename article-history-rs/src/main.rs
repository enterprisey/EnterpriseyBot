use std::{
    collections::HashMap,
    convert::TryInto,
    error::Error,
    iter,
    fs::{File, OpenOptions},
    io::{Read, Write},
    path,
};

use futures::stream::{Stream, StreamExt};
use itertools::Itertools;
use mediawiki::{api::Api, page::Page, title::Title};
use parse_wiki_text::{Configuration, Node, Parameter};

mod common;
mod dyk;
mod itn;
mod otd;

use common::make_map;

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

pub struct Template {
    name: TemplateType,
    unnamed: Vec<String>,
    named: linked_hash_map::LinkedHashMap<String, String>,
}

impl Template {
    fn into_wikitext(self) -> String {
        let are_any_named = !self.named.is_empty();
    "{{".to_string()
        + match self.name {
            TemplateType::ArticleHistory => "Article history",
            TemplateType::Dyk => "DYK talk",
            TemplateType::Itn => "ITN talk",
            TemplateType::Otd => "On this day",
        }
        + if !self.unnamed.is_empty() { "|" } else { "" }
        + &self.unnamed.join("|")
        + if are_any_named { "\n|" } else { "" }
        + &self.named
            .iter()
            .map(Some)
            .chain(iter::once(None))
            .tuple_windows()
            .map(|i| match i { (Some((k, v)), next_kv) => {
                const N: usize = "action".len();
                let need_newline = k.get(..N) == Some("action")
                    && next_kv.map_or(false, |(next_k, _next_v)| {
                        k.get(..N + 1) != next_k.get(..N + 1)
                    });
                format!(" {} = {}{}", k, v, if need_newline { "\n" } else { "" })
            }, _ => unreachable!()})
            .collect::<Vec<_>>()
            .join("\n|")
        + if are_any_named { "\n" } else { "" }
        + "}}"
    }
}

fn wikitext_to_template_list<'a>(
    wikitext: &'a str,
    page_name: &str,
    template_name_map: &HashMap<String, TemplateType>,
) -> Vec<(Template, (usize, usize))> {
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
                start,
                end,
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
                Some((Template {
                    name: template_type,
                    unnamed,
                    named,
                }, (start, end)))
            },
            _ => None,
        })
        .collect()
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
        for redirect in page["redirects"].as_array().into_iter().flatten() {
            map.insert(fix(redirect["title"].as_str().unwrap()), template_type);
        }
    }
    map
}

async fn process_page(api: &Api, title: &str) -> Result<String, Box<dyn Error>> {
    let page = Page::new(Title::new_from_full(title, &api));
    let text = page.text(&api).await?;

    let (zeroth_section, rest_of_page) = text.split_at(text.find("\n==").unwrap_or(text.len()));
    let mut zeroth_section = zeroth_section.to_string();

    let template_name_map = build_template_name_map(&api).await;
    let templates = wikitext_to_template_list(&zeroth_section, title, &template_name_map);

    let (mut all_article_history_templates, other_templates): (Vec<_>, Vec<_>) = templates
        .into_iter()
        .partition(|t| t.0.name == TemplateType::ArticleHistory);

    // There ought to be only one article history
    assert_eq!(all_article_history_templates.len(), 1, "{}", title);

    let (mut article_history, (article_history_start, article_history_end)) = all_article_history_templates.remove(0);
    let mut spans_before_article_history_to_remove = Vec::new();
    for &(ref template, (template_start, mut template_end)) in other_templates.iter().rev() {
        match template.name {
            TemplateType::Itn => common::update_article_history(
                itn::parse_itn_template(template), &mut article_history),
            TemplateType::Otd => common::update_article_history(
                otd::parse_otd_template(template), &mut article_history),
            TemplateType::Dyk => common::update_article_history(
                vec![dyk::parse_dyk_template(api, title, template).await.expect("dyk")],
                &mut article_history
            ),
            TemplateType::ArticleHistory => unreachable!(),
        }

        if zeroth_section.as_bytes()[template_end] == b'\n' {
            template_end += 1;
        }

        if template_start > article_history_end {
            zeroth_section.replace_range(template_start..template_end, "");
        } else {
            spans_before_article_history_to_remove.push((template_start, template_end));
        }
    }
    zeroth_section.replace_range(article_history_start..article_history_end,
            &article_history.into_wikitext());
    let new_text = zeroth_section + rest_of_page;
    Ok(new_text)
}

async fn get_pages_to_fix<'a>(api: &'a Api, starting_title: Option<String>) -> impl Stream<Item = String> + 'a {
    let mut params = make_map(&[
        ("action", "query"),

        // I wish we could use the embeddedin generator, but that doesn't let
        // you pick the page to start from, so we'd be starting from the
        // beginning but running for longer and longer each time. This way,
        // we're going through a lot more pages, but at least we're wasting
        // a constant amount of time each time.
        ("generator", "allpages"),
        ("gapnamespace", "1"), // talk pages
        ("gaplimit", "50"),
        ("prop", "templates"),
        ("tltemplates", "Template:Article history|Template:ITN talk|Template:On this day|Template:DYK talk"),
        ("formatversion", "2"),
    ]);
    if let Some(starting_title) = starting_title {
        params.insert("gapfrom".to_string(), starting_title.to_string());
    }
    api.get_query_api_json_limit_iter(&params, None).await
        .flat_map(move |data| if data.is_ok() {
            let data = data.unwrap();
            if data["query"]["pages"].as_array().is_some() {
                futures::stream::iter(data["query"]["pages"].as_array().unwrap().clone())
            } else {
                panic!("bad response to {:?}, no array: {:?}", params.clone(), data)
            }
        } else {
            panic!("bad response to {:?}: res {:?}", params.clone(), data)
        })
        .filter_map(|page| {
            let mut has_article_history = false;
            let mut has_other_template = false;
            for template in page["templates"].as_array().into_iter().flatten() {
                if template["title"].as_str() == Some("Template:Article history") {
                    has_article_history = true;
                } else {
                    has_other_template = true;
                }

                if has_article_history && has_other_template {
                    break;
                }
            }

            futures::future::ready(if has_article_history && has_other_template {
                Some(page["title"].as_str().unwrap().to_string())
            } else {
                None
            })
        })
}

fn load_progress(filename: &str) -> Result<Option<String>, Box<dyn Error>> {
    if path::Path::new(filename).exists() {
        let mut file = File::open(&filename)?;
        let mut contents = String::new();
        file.read_to_string(&mut contents)?;
        Ok(Some(contents.trim().to_string()))
    } else {
        Ok(None)
    }
}

fn save_progress(filename: String, article: String) -> Result<(), Box<dyn Error>> {
    let mut file = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(filename)?;
    file.write_all(&article.into_bytes())?;
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let mut config = config::Config::default();
    config
        .merge(config::File::with_name("settings"))?
        .merge(config::Environment::with_prefix("APP"))?;
    let username = config.get_str("username")?;
    let password = config.get_str("password")?;

    let edits_per_session: usize = config.get_int("edits_per_session")?.try_into()?;
    let progress_filename = config.get_str("progress_file")?;

    let mut api = Api::new("https://en.wikipedia.org/w/api.php").await?;
    api.login(username, password).await?;
    api.set_user_agent(format!("EnterpriseyBot/article-history-rs/{} (https://en.wikipedia.org/wiki/User:EnterpriseyBot; apersonwiki@gmail.com)", env!("CARGO_PKG_VERSION")));

    let mut edit_list: Vec<(String, String)> = Vec::new(); // (title, new text)
    let mut titles = Box::pin(get_pages_to_fix(&api, load_progress(&progress_filename)?).await);
    while let Some(page_title) = titles.next().await {
        let new_text = process_page(&api, &page_title).await.unwrap();
        edit_list.push((page_title.clone(), new_text));
        if edit_list.len() >= edits_per_session {
            break;
        }
    }
    std::mem::drop(titles);

    if let Some((final_title, _)) = edit_list.get(edit_list.len().saturating_sub(1)) {
        save_progress(progress_filename, final_title["Talk:".len()..].to_string())?;
    }

    for (title, new_text) in edit_list.into_iter() {
        Page::new(Title::new_from_full(&title, &api)).edit_text(&mut api, new_text, SUMMARY).await?;
    }
    Ok(())
}
