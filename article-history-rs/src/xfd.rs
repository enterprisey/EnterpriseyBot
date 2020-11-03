use std::borrow::Cow;

use regex::Regex;

use super::Parameters;
use crate::common::fuzzy_parse_timestamp;

pub struct Xfd {
    date: String,

    /// Page where the discussion took place.
    page: Option<String>,

    result: String,
}

lazy_static::lazy_static! {
    static ref DATE: Regex = Regex::new(r"\d{1,2} \w+? \d{4}").unwrap();
}

//async fn get_close_date_from_afd_page(api: &Api, title: &str) -> Option<String> {
//    let page = Page::new(Title::new_from_full(title, &api));
//    let text = page.text(&api).await?;
//    DATE.find(text).map(|m| m.as_str().to_string())
//}

fn sanitize_title<'a>(title: &str) -> Result<String, String> {
    let mut title = percent_encoding::percent_decode(title.as_bytes()).decode_utf8().map_err(|e| format!("{}", e))?;
    if let Some(idx) = title.find('|') {
        title = Cow::Owned((&title[..idx]).to_string());
    }
    Ok(title.as_ref().chars().filter(|&c| c != '[' && c != ']' && c != '{' && c != '}').collect())
}

fn require_afd_prefix(title: &str) -> String {
    let is_title_in_wikipedia_space = {
        let lowered = title.to_lowercase();
        lowered.starts_with("wp:articles for deletion/") || lowered.starts_with("wikipedia:articles for deletion/")
    };
    if is_title_in_wikipedia_space {
        title.to_string()
    } else {
        format!("Wikipedia:Articles for deletion/{}", title)
    }
}

fn sanitize_result(result: &str) -> &str {
    assert!(result.chars().all(|c| c.is_ascii_alphabetic() || c == '\'' || c == ' '));
    if result.starts_with("'''") && result.ends_with("'''") {
        &result[3 .. result.len() - 3]
    } else {
        result
    }
}

pub fn params_to_xfd(
    article_title: &str,
    params: &Parameters,
) -> Result<Vec<Xfd>, String> {
    if !params.get("type").map_or(true, |t| t == "article" || t == "page") {
        return Err("type parameter isn't article!".to_string());
    }

    if params.keys().any(|key| key.starts_with("link")) {

        // The article history template cannot take bare URLs as the link for an XfD event
        return Err("link (or link2, link3, etc.) parameter specified!".to_string());
    }

    // TODO I know there's some default behavior involving checking if pages
    // exist and such, but that's too complicated for now.
    let date1 = params.get("date").or(params.get("date1")).ok_or("No `date` param!")?;

    let page1 = params.get("page")
        .or(params.get("page1"))
        .or(params.get("votepage"))
        .or(params.get("votepage1"))
        .map(|s| sanitize_title(s))
        .unwrap_or_else(|| {
            println!("warning: falling back to article title for xfd #1 at {}", article_title);
            Ok(article_title.to_string())
        });
    let page1 = require_afd_prefix(&(page1?));

    let default_to_keep = |result: Option<_>| result.map(ToString::to_string).unwrap_or_else(|| {
        println!("warning: assuming AfD result #1 for {} was Keep", article_title);
        "keep".to_string()
    });
    let result1 = default_to_keep(params.get("result").or(params.get("result1")).map(String::as_ref).map(sanitize_result));

    let xfd1 = Xfd { date: date1.to_string(), page: Some(page1), result: result1.to_string() };

    if let Some(first_num_without_date) = (2..).find(|num| !params.contains_key(&format!("date{}", num))) {
        Ok(std::iter::once(xfd1).chain((2..first_num_without_date).into_iter().map(|num| {
            let param = |prefix| params.get(&format!("{}{}", prefix, num));
            Xfd {
                date: param("date").unwrap().to_string(),
                page: param("page").or(param("votepage")).map(|s| require_afd_prefix(s)),
                result: default_to_keep(param("result").map(String::as_ref).map(sanitize_result)),
            }
        })).collect())
    } else {
        Ok(vec![xfd1])
    }
}

pub fn xfd_to_action(xfd: Xfd) -> Result<super::Action, dtparse::ParseError> {
    let parsed_date = fuzzy_parse_timestamp(&xfd.date)?;
    Ok(super::Action {
        code: "AFD".to_string(),
        date: xfd.date,
        parsed_date: parsed_date,
        link: xfd.page,
        result: Some(xfd.result),
        oldid: None,
    })
}
