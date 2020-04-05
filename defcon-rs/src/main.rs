use std::collections::HashMap;
use std::error::Error;

use chrono::{prelude::*, Duration};
use config;
use lazy_static::lazy_static;
use mediawiki::api::Api;
use regex::Regex;

mod fixed_api;

static VANDALISM_KEYWORDS: [&str; 8] = ["revert", "rv ", "long-term abuse", "long term abuse",
    "lta", "abuse", "rvv ", "undid"];
static NOT_VANDALISM_KEYWORDS: [&str; 12] = ["uaa", "good faith", "agf", "unsourced",
    "unreferenced", "self", "speculat", "original research", "rv tag", "typo", "incorrect", "format"];
static ISO_8601_FMT: &str = "%Y-%m-%dT%H:%M:%SZ";
static INTERVAL_IN_MINS: i64 = 60;
static PAGE_NAME: &str = "User:EnterpriseyBot/defcon";

lazy_static! {
    static ref SECTION_HEADER_RE: Regex = Regex::new(r"/\*[\s\S]+?\*/").unwrap();
    static ref LEVEL_RE: Regex = Regex::new(r"level\s*=\s*(\d+)").unwrap();
}

fn make_map(params: &[(&str, &str)]) -> HashMap<String, String> {
    params.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
}

fn is_revert_of_vandalism(edit_summary: &str) -> bool {
    let edit_summary = SECTION_HEADER_RE.replace(edit_summary, "");
    for not_vand_kwd in NOT_VANDALISM_KEYWORDS.iter() {
        if edit_summary.contains(not_vand_kwd) {
            return false;
        }
    }

    for vand_kwd in VANDALISM_KEYWORDS.iter() {
        if edit_summary.contains(vand_kwd) {
            println!("{}", &edit_summary);
            return true;
        }
    }

    false
}

fn reverts_per_minute(api: &Api) -> Result<f32, Box<dyn Error>> {
    let time_one_interval_ago = Utc::now() - Duration::minutes(INTERVAL_IN_MINS);
    let end_str = time_one_interval_ago.format(ISO_8601_FMT).to_string();
    let query = make_map(&[
        ("action", "query"),
        ("list", "recentchanges"),
        ("rctype", "edit"),
        ("rcstart", &Utc::now().format(ISO_8601_FMT).to_string()),
        ("rcend", &end_str),
        ("rcprop", "comment"),
        ("rclimit", "100"),
        ("rcshow", "!bot"),
    ]);
    let res = fixed_api::get_query_api_json_limit(&api, &query, /* limit */ None)?;
    let num_reverts = res["query"]["recentchanges"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|edit| is_revert_of_vandalism(edit["comment"].as_str().unwrap_or("")))
        .count();
    Ok((num_reverts as f32) / (INTERVAL_IN_MINS as f32))
}

fn rpm_to_level(rpm: f32) -> u8 {
    if rpm <= 2.0 {
        5
    } else if rpm <= 4.0 {
        4
    } else if rpm <= 6.0 {
        3
    } else if rpm <= 8.0 {
        2
    } else {
        1
    }
}

fn get_page_text(api: &Api, title: &str) -> Result<String, Box<dyn Error>> {
    let res = api.get_query_api_json(&make_map(&[
        ("action", "query"),
        ("prop", "revisions"),
        ("titles", title),
        ("rvprop", "content"),
        ("rvslots", "main"),
    ]))?;
    Ok(res["query"]["pages"]
        .as_object().ok_or("no json object under result.query.pages")?
        .values().next().ok_or("no pages returned")?
        ["revisions"][0]["slots"]["main"]["*"].as_str()
        .ok_or("page content wasn't a string")?.to_string())
}

fn set_page_text(api: &mut Api, title: &str, new_text: String, summary: String) -> Result<(), Box<dyn Error>> {
    let token = api.get_edit_token().unwrap();
    api.post_query_api_json(&make_map(&[
        ("action", "edit"),
        ("title", title),
        ("text", new_text.as_str()),
        ("token", &token),
        ("summary", &summary),
    ]))?;
    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut config = config::Config::default();
    config
        .merge(config::File::with_name("settings"))?
        .merge(config::Environment::with_prefix("APP"))?;
    let username = config.get_str("username")?;
    let password = config.get_str("password")?;

    let mut api = Api::new("https://en.wikipedia.org/w/api.php")?;
    api.login(username, password)?;

    // get current on-wiki defcon level
    let curr_text = get_page_text(&api, PAGE_NAME)?;
    let curr_level = if let Some(captures) = LEVEL_RE.captures(&curr_text) {
        captures.get(1).unwrap().as_str().parse::<u8>().unwrap()
    } else {
        0
    };

    // compute current defcon level
    let rpm = reverts_per_minute(&api)?;
    let level = rpm_to_level(rpm);

    if curr_level != level {
        let text = format!("{{{{#switch: {{{{{{1}}}}}}
              | level = {}
              | sign = ~~~~~
              | info = {:.2} RPM according to [[User:EnterpriseyBot|EnterpriseyBot]]
            }}}}", level, rpm);
    let summary = format!("[[Wikipedia:Bots/Requests for approval/APersonBot 5|Bot]] updating vandalism level to level {0} ({1:.2} RPM) #DEFCON{0}", level, rpm);
        set_page_text(&mut api, PAGE_NAME, text, summary)?;
    }
    Ok(())
}
