use std::collections::HashMap;
use std::error::Error;

use chrono::{prelude::*, Duration};
use config;
use lazy_static::lazy_static;
use mediawiki::{
    api::Api,
    page::Page,
    title::Title,
};
use regex::Regex;

static VANDALISM_KEYWORDS: [&str; 8] = ["revert", "rv ", "long-term abuse", "long term abuse",
    "lta", "abuse", "rvv ", "undid"];
static NOT_VANDALISM_KEYWORDS: [&str; 12] = ["uaa", "good faith", "agf", "unsourced",
    "unreferenced", "self", "speculat", "original research", "rv tag", "typo", "incorrect", "format"];
static ISO_8601_FMT: &str = "%Y-%m-%dT%H:%M:%SZ";
static INTERVAL_IN_MINS: i64 = 60;

lazy_static! {
    static ref SECTION_HEADER_RE: Regex = Regex::new(r"/\*[\s\S]+?\*/").unwrap();
    static ref LEVEL_RE: Regex = Regex::new(r"level\s*=\s*(\d+)").unwrap();
}

fn make_map(params: &[(&str, &str)]) -> HashMap<String, String> {
    params.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
}

fn is_revert_of_vandalism(edit_summary: &str) -> bool {
    let edit_summary = SECTION_HEADER_RE.replace(edit_summary, "")
        .to_ascii_lowercase();
    for not_vand_kwd in NOT_VANDALISM_KEYWORDS.iter() {
        if edit_summary.contains(not_vand_kwd) {
            return false;
        }
    }

    for vand_kwd in VANDALISM_KEYWORDS.iter() {
        if edit_summary.contains(vand_kwd) {
            return true;
        }
    }

    false
}

async fn reverts_per_minute(api: &Api) -> Result<f32, Box<dyn Error>> {
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
    ]);
    let res = api.get_query_api_json_all(&query).await?;
    let num_reverts = res["query"]["recentchanges"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|edit| edit["comment"].as_str().map_or(false, is_revert_of_vandalism))
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

    api.set_user_agent(format!("EnterpriseyBot/defcon-rs/{} (https://en.wikipedia.org/wiki/User:EnterpriseyBot; apersonwiki@gmail.com)", env!("CARGO_PKG_VERSION")));

    // get current on-wiki defcon level
    let report_page = config.get_str("report_page")?;
    let page = Page::new(Title::new_from_full(&report_page, &api));
    let curr_text = page.text(&api).await?;
    let curr_level = if let Some(captures) = LEVEL_RE.captures(&curr_text) {
        captures.get(1).unwrap().as_str().parse::<u8>().unwrap()
    } else {
        0
    };

    // compute current defcon level
    let rpm = reverts_per_minute(&api).await?;
    let level = rpm_to_level(rpm);

    if curr_level != level {
        let text = format!("{{{{#switch: {{{{{{1}}}}}}
              | level = {}
              | sign = ~~~~~
              | info = {:.2} RPM according to [[User:EnterpriseyBot|EnterpriseyBot]]
            }}}}", level, rpm);
        let summary = format!("[[Wikipedia:Bots/Requests for approval/APersonBot 5|Bot]] updating vandalism level to level {0} ({1:.2} RPM) #DEFCON{0}", level, rpm);
        page.edit_text(&mut api, text, summary).await?;
    } else {
        // No edit necessary
    }
    Ok(())
}
