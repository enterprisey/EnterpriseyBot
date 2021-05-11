use std::{
    collections::HashMap,
    convert::TryInto,
    error::Error,
    fs::{File, OpenOptions},
    io::{Read, Write},
    iter,
    path,
};

use chrono::NaiveDateTime;
use futures::stream::{Stream, StreamExt};
use itertools::{Either, Itertools};
use mediawiki::{api::Api, page::Page, title::Title};
use parse_wiki_text::{Configuration, Node, Parameter};
use strum::IntoEnumIterator;
use strum_macros::EnumIter;

mod common;
mod dyk;
mod itn;
mod otd;
mod xfd;

use common::{make_map, WikitextTransform};

const SUMMARY: &str = "[[Wikipedia:Bots/Requests for approval/APersonBot 7|Bot]] merging redundant talk page banners into [[Template:Article history]].";

// as of MW 1.35, the revision table has rev_id as a int(10) unsigned
type RevId = u32;

pub type Parameters = linked_hash_map::LinkedHashMap<String, String>;

#[derive(Debug,Clone,Copy,PartialEq,Eq,Hash,EnumIter)]
enum TemplateType {
    Dyk,
    Itn,
    Otd,
    Xfd,
}

impl TemplateType {
    fn get_template_title(&self) -> &'static str {
        use TemplateType::*;
        match self {
            Dyk => "Template:DYK talk",
            Itn => "Template:ITN talk",
            Otd => "Template:On this day",
            Xfd => "Template:Old XfD multi",
        }
    }
}

#[derive(Debug,Clone,Copy,PartialEq,Eq,Hash)]
pub struct ArticleHistoryTemplateType;

type TemplateNameMap = HashMap<String, Either<ArticleHistoryTemplateType, TemplateType>>;

#[derive(Debug)]
pub struct OtherTemplate {
    kind: TemplateType,
    unnamed: Vec<String>,
    named: Parameters,
}

pub struct Action {
    code: String,
    date: String,
    parsed_date: NaiveDateTime,
    link: Option<String>,
    result: Option<String>,
    oldid: Option<String>, // TODO figure these out from the timestamp, shouldn't be hard
}

pub struct ArticleHistory {
    actions: Vec<Action>,
    other: Parameters,
}

pub struct Spanned<T> {
    start: usize,
    end: usize,
    item: T,
}

impl ArticleHistory {
    fn from_params(mut params: Parameters) -> Result<Self, String> {
        let highest_code_number = (1..).find(|num| !params.contains_key(&format!("action{}", num))).unwrap_or(0);
        let highest_date_number = (1..).find(|num| !params.contains_key(&format!("action{}date", num))).unwrap_or(0);

        if highest_code_number != highest_date_number {
            return Err(format!(
                "highest_code_number ({}) did not equal highest_date_number ({}): full params {:?}",
                highest_code_number, highest_date_number, params
            ));
        }

        let actions = (1..highest_date_number).map(|num| {
            let prefix = format!("action{}", num);
            let date_key = prefix.clone() + "date";
            let parsed_date = common::fuzzy_parse_timestamp(&params[&date_key]).expect("dtparse");
            Action {
                code: params.remove(&prefix).unwrap(),
                date: params.remove(&date_key).unwrap(),
                parsed_date,
                link: params.remove(&(prefix.clone() + "link")),
                oldid: params.remove(&(prefix.clone() + "oldid")),
                result: params.remove(&(prefix + "result")),
            }
        }).collect();

        Ok(ArticleHistory {
            actions,
            other: params,
        })
    }

    fn into_wikitext(self) -> String {
        let any_actions = !self.actions.is_empty();
        "{{Article history\n".to_string()
            + &self.actions.into_iter().enumerate()
                .map(
                    |(idx, Action { code, date, parsed_date: _, link, result, oldid })| {
                        format!(
                            "| action{0} = {1}\n| action{0}date = {2}{3}{4}{5}",
                            idx + 1,
                            code,
                            date,
                            link.map_or("".into(), |l| format!("\n| action{}link = {}", idx + 1, l)),
                            result.map_or("".into(), |l| format!("\n| action{}result = {}", idx + 1, l)),
                            oldid.map_or("".into(), |l| format!("\n| action{}oldid = {}", idx + 1, l))
                        )
                    },
                )
                .collect::<Vec<_>>()
                .join("\n\n")
            + if any_actions { "\n\n|" } else { "" }
            + &self
                .other
                .iter()
                .map(|(k, v)| format!(" {} = {}", k, v))
                .collect::<Vec<_>>()
                .join("\n|")
            + if any_actions { "\n" } else { "" }
            + "}}"
    }
}

fn wikitext_to_template_list<'a>(
    wikitext: &'a str,
    page_name: &str,
    template_name_map: &TemplateNameMap,
) -> (Vec<Spanned<ArticleHistory>>, Vec<Spanned<OtherTemplate>>) {
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
                let template_name = common::nodes_to_text(&name_nodes, WikitextTransform::RequirePureText).unwrap_or_else(|e|
                    panic!(
                        "while handling '{}': nodes_to_text failed on template name: {}",
                        page_name, e
                    ));
                let template_type = if let Some(t) = template_name_map.get(common::uppercase_first_letter(template_name.as_ref()).as_ref()) {
                    *t
                } else {
                    return None;
                };
                let (named, unnamed): (Vec<_>, Vec<_>) = parameters
                    .iter()
                    .enumerate()
                    .map(|(param_idx, Parameter { name: name_nodes, value: value_nodes, .. })| {
                        let param_name = name_nodes.as_ref().map(|name_nodes| common::nodes_to_text(&name_nodes, WikitextTransform::RequirePureText)
                            .unwrap_or_else(|e| panic!(
                                "while handling page '{}', template '{}': nodes_to_text failed on the name of parameter index {}: {}",
                                page_name, template_name, param_idx, e
                            )));
                        let param_value = common::nodes_to_text(&value_nodes, WikitextTransform::KeepMarkup)
                            .unwrap_or_else(|e| panic!(
                                "while handling page '{}', template '{}': nodes_to_text failed on the value for parameter '{:?}' (index {}): {}",
                                page_name, template_name, param_name, param_idx, e
                            ));
                        (param_name, param_value)
                    }).partition(|(name, _value)| name.is_some());
                let named = named.into_iter().map(|(name, value)| (name.unwrap().into_owned(), value.into_owned())).collect();
                let unnamed = unnamed.into_iter().map(|(_name, value)| value.into_owned()).collect::<Vec<_>>();
                let template = match template_type {
                    Either::Left(ArticleHistoryTemplateType) => {
                        assert!(unnamed.is_empty());
                        Either::Left(Spanned { start, end, item: ArticleHistory::from_params(named).unwrap() })
                    },
                    Either::Right(other_type) => Either::Right(Spanned { start, end, item: OtherTemplate {
                        kind: other_type,
                        unnamed,
                        named,
                    } }),
                };
                Some(template)
            },
            _ => None,
        })
        .partition_map(std::convert::identity)
}

async fn build_template_name_map(api: &Api) -> TemplateNameMap {
    let all_template_titles = TemplateType::iter().map(|t| t.get_template_title()).collect::<Vec<_>>().join("|");
    let res = api.get_query_api_json_all(&make_map(&[
        ("action", "query"),
        ("titles", &all_template_titles),
        ("prop", "redirects"),
        ("formatversion", "2"),
    ])).await.expect("build_template_name_map");
    let mut map = HashMap::new();
    let title_to_template_type_map: HashMap<&'static str, TemplateType> = TemplateType::iter()
        .map(|t| (t.get_template_title(), t))
        .collect();
    let title_to_template_type = |s| -> Either<ArticleHistoryTemplateType, TemplateType> {
        match s {
            "Template:Article history" => Either::Left(ArticleHistoryTemplateType),
            _ => if let Some(kind) = title_to_template_type_map.get(s) {
                    Either::Right(*kind)
                } else {
                    panic!("main.rs:{} {}", line!(), s)
                },
        }
    };
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

async fn process_page(api: &Api, title: &str, text: &str, template_name_map: &TemplateNameMap) -> Result<String, Box<dyn Error>> {
    dbg!(title);

    let (zeroth_section, rest_of_page) = text.split_at(text.find("\n==").unwrap_or(text.len()));
    let mut zeroth_section = zeroth_section.to_string();

    let (mut all_article_history_templates, other_templates) =
        wikitext_to_template_list(&zeroth_section, title, template_name_map);

    if all_article_history_templates.is_empty() {
        let location_for_article_history = zeroth_section.len();
        all_article_history_templates.push(Spanned {
            item: ArticleHistory {
                actions: Vec::new(),
                other: linked_hash_map::LinkedHashMap::new(),
            },
            start: location_for_article_history,
            end: location_for_article_history,
        });
    }

    // There ought to be only one article history
    assert_eq!(all_article_history_templates.len(), 1, "{}", title);

    let Spanned { item: article_history, start: article_history_start, end: article_history_end } = all_article_history_templates.remove(0);
    let mut article_history: ArticleHistory = article_history.try_into().unwrap();
    let mut spans_before_article_history_to_remove = Vec::new();
    for &Spanned { item: ref template, start: template_start, end: mut template_end } in other_templates.iter().rev() {
        match template.kind {
            TemplateType::Itn => common::update_article_history(
                itn::parse_itn_template(template).unwrap_or_else(|e| panic!("itn at {}: {}", title, e)), &mut article_history.other),
            TemplateType::Otd => common::update_article_history(
                otd::parse_otd_template(template), &mut article_history.other),
            TemplateType::Dyk => common::update_article_history(
                vec![dyk::parse_dyk_template(api, title, template).await.unwrap_or_else(|e| panic!("dyk at {}: {}", title, e))],
                &mut article_history.other
            ),
            TemplateType::Xfd => {
                let new_actions = xfd::params_to_xfd(title, &template.named).unwrap_or_else(|e| panic!("xfd at {}: {}", title, e))
                    .into_iter().map(|x| xfd::xfd_to_action(x).unwrap_or_else(|e| panic!("xfd conversion at {}: {}", title, e)));
                article_history.actions.extend(new_actions);
                article_history.actions.sort_by_key(|action| action.parsed_date);
            }
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

    for (start, end) in spans_before_article_history_to_remove {
        zeroth_section.replace_range(start..end, "");
    }

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
        ("tltemplates",
            &TemplateType::iter()
                .map(|t| t.get_template_title())
                .chain(iter::once("Template:Article history"))
                .collect::<Vec<_>>()
                .join("|")
        ),
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
            // TODO three or more regular templates should trigger an edit even if there's no
            // article history
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

    let edits_per_session: usize = config.get_int("edits_per_session")?.try_into()?;
    let progress_filename = config.get_str("progress_file")?;

    #[cfg(test)]
    let mut api = Api::new(&mockito::server_url()).await?;

    #[cfg(not(test))]
    let mut api = {
        let mut api = Api::new("https://en.wikipedia.org/w/api.php").await?;
        let username = config.get_str("username")?;
        let password = config.get_str("password")?;
        api.login(username, password).await?;
        api
    };

    api.set_user_agent(format!("EnterpriseyBot/article-history-rs/{} (https://en.wikipedia.org/wiki/User:EnterpriseyBot; apersonwiki@gmail.com)", env!("CARGO_PKG_VERSION")));

    let template_name_map = build_template_name_map(&api).await;

    let mut edit_list: Vec<(String, String)> = Vec::new(); // (title, new text)
    let mut titles = Box::pin(get_pages_to_fix(&api, load_progress(&progress_filename)?).await);
    while let Some(page_title) = titles.next().await {
        let page = Page::new(Title::new_from_full(&page_title, &api));
        let text = page.text(&api).await?;
        let new_text = process_page(&api, &page_title, &text, &template_name_map).await.unwrap();
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
