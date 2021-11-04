use std::{
    borrow::Cow,
    collections::HashMap,
};

use parse_wiki_text::Node;

use crate::{Parameters, OtherTemplate};

// Why? Because MediaWiki (and thus Wikipedia) titles are case-sensitive in all
// but the first character.
pub fn uppercase_first_letter(string: &str) -> Cow<'_, str> {
    if let Some(first_char) = string.chars().nth(0) {
        if first_char.is_ascii_lowercase() {
            Cow::Owned(format!("{}{}", first_char.to_ascii_uppercase(), &string[1..]))
        } else {
            Cow::Borrowed(string)
        }
    } else {
        Cow::Borrowed(string)
    }
}

fn remove_final_utc(timestamp: &str) -> &str {
    if timestamp.ends_with(" (UTC)") {
        &timestamp[..timestamp.len() - 6]
    } else {
        timestamp
    }
}

pub fn fuzzy_parse_timestamp(timestamp: &str) -> Result<chrono::naive::NaiveDateTime, dtparse::ParseError> {
    dtparse::parse(remove_final_utc(timestamp)).map(|(date, _time)| date)
}

pub fn make_map(params: &[(&str, &str)]) -> HashMap<String, String> {
    params.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
}

pub fn get_template_param_2<'a, 'b>(template: &'a OtherTemplate, key1: impl Into<Cow<'b, str>>, key2: impl Into<Cow<'b, str>>) -> &'a str {
    //template.named.get(key1.into().as_ref()).map_or_else(|| template.named.get(key2.into().as_ref()).map_or("", Cow::as_ref), Cow::as_ref).trim()
    template
        .named
        .get(key1.into().as_ref())
        .map_or_else(
            || template.named.get(key2.into().as_ref()).map_or("", String::as_ref),
            String::as_ref,
        )
        .trim()
}

pub fn get_template_param<'a, 'b>(template: &'a OtherTemplate, key1: impl Into<Cow<'b, str>>) -> &'a str {
    template.named.get(key1.into().as_ref()).map_or("", String::as_ref).trim()
}

#[derive(Clone, Copy)]
pub enum WikitextTransform { RequirePureText, GetTextContent, KeepMarkup }

pub fn nodes_to_text<'a>(nodes: &[Node<'a>], transform: WikitextTransform) -> Result<Cow<'a, str>, String> {
    let error_msg = format!("unknown node type encountered: {:?}", &nodes);
    use Node::*;
    use WikitextTransform::*;
    use Cow::*;
    nodes.iter().map(|node| match (node, transform) {
        (Text { value, .. }, _) => Ok(Borrowed(*value)),
        (_, RequirePureText) => Err(()),
        (Bold { .. }, KeepMarkup) => Ok(Borrowed("'''")),
        (Italic { .. }, KeepMarkup) => Ok(Borrowed("''")),
        (BoldItalic { .. }, KeepMarkup) => Ok(Borrowed("'''''")),
        (Bold { .. }, GetTextContent) | (Italic { .. }, GetTextContent) | (BoldItalic { .. }, GetTextContent) => Ok(Borrowed("")),
        (Link { text, .. }, GetTextContent) => nodes_to_text(text, GetTextContent).map_err(|_| ()),
        (Link { target, text, .. }, KeepMarkup) => nodes_to_text(text, KeepMarkup).map_or_else(|_| Err(()), |wikitext| Ok(Owned(format!("[[{}|{}]]", target, wikitext)))),
        _ => Err(()),
    }).collect::<Result<Vec<_>, _>>().map_or_else(
        |()| Err(error_msg),
        |mut values| if values.len() == 1 {
            Ok(values.remove(0))
        } else {
            Ok(Cow::Owned(values.join("")))
        }
    )
}

pub trait ToParams<'a> {
    const PREFIX: &'static str;
    type Iter: Iterator<Item = (&'static str, Cow<'a, str>)>; // (key suffix (like "date"), value (like "2020-09-13"))
    fn to_params(self) -> Self::Iter;
}

/// Counts how many "date" params are specified for the given prefix in the
/// given {{article history}} transclusion.
fn count_existing_entries<'a, T: ToParams<'a>>(params: &Parameters) -> usize {
    if params.contains_key(&format!("{}{}", T::PREFIX, "date")) {
        (2..)
            .into_iter()
            .find(|idx| !params.contains_key(&format!("{}{}date", T::PREFIX, idx)))
            .unwrap() // if this doesn't work, then there were an infinite number of parameters!
            - 1 // the find will return the first number WITHOUT an entry,
                // but the numbers are 1-indexed so the count will be 1 less
    } else {
        0
    }
}

pub fn update_article_history<'a, T: ToParams<'a>>(entries: Vec<T>, params: &mut Parameters) {
    let num_existing_entries = count_existing_entries::<T>(params);

    fn get_param_prefix<'a, T: ToParams<'a>>(idx: usize) -> String {
        match idx {
            0 => T::PREFIX.into(),
            _ => format!("{}{}", T::PREFIX, idx + 1),
        }
    }

    params.extend(entries
        .into_iter()
        .map(ToParams::to_params)
        .zip(num_existing_entries..) // i.e. if there are 2 existing entries, the first new index will be 3
        .flat_map(|(params, idx): (T::Iter, usize)| {
            params.map(move |(suffix, value)| (get_param_prefix::<T>(idx) + suffix, value.into_owned()))
        }),
    );
}

pub enum PageExistenceResult {
    PrimaryExists,
    BackupExists,
    NeitherExist,
}

pub async fn try_page_existence(api: &mediawiki::api::Api, primary_title: &str, backup_title: &str) -> Result<PageExistenceResult, String> {
    let res = api.get_query_api_json(&make_map(&[
        ("action", "query"),
        ("titles", &format!("{}|{}", primary_title, backup_title)),
        ("formatversion", "2"),
    ])).await.map_err(|e| format!("API error: {:?}", e))?;
    let mut does_primary_exist = true;
    let mut does_backup_exist = true;
    for page in res["query"]["pages"].as_array().ok_or(format!("no pages in res: {:?}", res))? {
        let page_title = page["title"].as_str().ok_or(format!("no title for page: full res {:?}", res))?;
        let is_page_missing = page["missing"].as_bool().unwrap_or(false);
        if page_title == primary_title && is_page_missing {
            does_primary_exist = false;
        } else if page_title == backup_title && is_page_missing {
            does_backup_exist = false;
        } else {
            return Err(format!("unrecognized title {}: full response {:?}", page_title, res));
        }
    }

    Ok(match (does_primary_exist, does_backup_exist) {
        (true, _) =>      PageExistenceResult::PrimaryExists,
        (false, true) =>  PageExistenceResult::BackupExists,
        (false, false) => PageExistenceResult::NeitherExist,
    })
}
