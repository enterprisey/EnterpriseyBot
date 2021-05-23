use std::collections::HashMap;
use std::error::Error;

use mediawiki::{
    api_sync::ApiSync,
};

const CATEGORY_NAMESPACE: &str = "14";

fn ends_in_four_digits(s: &str) -> bool {
    s.chars().rev().take(4).all(|c: char| c.is_ascii_digit())
}

fn make_map(params: &[(&str, &str)]) -> HashMap<String, String> {
    params.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
}

fn make_nonnegative(i: i64) -> u64 {
    if i < 0 {
        0
    } else {
        i as u64
    }
}

/// recursively get total category size given title and categoryinfo
fn size(api: &ApiSync, category_title: &str, categoryinfo: &serde_json::Value, never_recurse: bool) -> Result<u64, Box<dyn Error>> {
    // can't use u64 because sometimes the API returns negative numbers for these values (????)
    let mut total =
        make_nonnegative(categoryinfo["pages"].as_i64().ok_or(format!(
            "categoryinfo.pages '{}' '{:?}' '{:?}'",
            category_title, categoryinfo["pages"], categoryinfo
        ))?) + make_nonnegative(categoryinfo["files"].as_i64().ok_or("categoryinfo.files")?);
    let num_subcats = make_nonnegative(categoryinfo["subcats"].as_i64().ok_or("categoryinfo.subcats")?);
    if num_subcats > 0 {
        if never_recurse {
            total += num_subcats;
        } else {
            for subcats_page in api.get_query_api_json_limit_iter(&make_map(&[
                ("action", "query"),

                ("generator", "categorymembers"),
                ("gcmtitle", category_title),
                ("gcmnamespace", CATEGORY_NAMESPACE),
                ("gcmtype", "subcat"),

                ("prop", "categoryinfo"),

                ("formatversion", "2"),
                ("format", "json"),
            ]), /* limit */ None) {
                let x = format!("{:?}", subcats_page);
                for subcat in subcats_page?["query"]["pages"].as_array().ok_or(format!("subcats_page.query.pages: {} {} {:?}", &category_title, &categoryinfo, x))? {
                    total += size(
                        api,
                        subcat["title"].as_str().ok_or("subcat.title")?,
                        &subcat["categoryinfo"],
                        false,
                    )?;
                }
            }
        }
    }
    Ok(total)
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut config = config::Config::default();
    config
        .merge(config::File::with_name("settings"))?
        .merge(config::Environment::with_prefix("APP"))?;
    let username = config.get_str("username")?;
    let password = config.get_str("password")?;
    let api_url = config.get_str("api_url")?;
    let mut api = ApiSync::new(&api_url)?;
    api.login(username, password)?;
    api.set_user_agent(format!("EnterpriseyBot/{}/{} (https://en.wikipedia.org/wiki/User:EnterpriseyBot; apersonwiki@gmail.com)", env!("CARGO_PKG_NAME"), env!("CARGO_PKG_VERSION")));

    let cat_track_template_name = config.get_str("cat_track_template_name")?;
    let never_recurse_list = config.get_array("never_recurse_list")?.into_iter().map(|v| v.into_str().unwrap()).collect::<Vec<String>>();
    let tracked_categories = api.get_query_api_json_limit_iter(&make_map(&[
        ("action", "query"),

        ("generator", "embeddedin"),
        ("geititle", &cat_track_template_name),
        ("geinamespace", CATEGORY_NAMESPACE),

        ("prop", "categoryinfo"),

        ("formatversion", "2"),
        ("format", "json"),
    ]), /* limit */ None);
    let mut counts: HashMap<String, u64> = HashMap::new();
    for tracked_cat_result_page in tracked_categories {
        let tracked_cat_result_page = tracked_cat_result_page?;
        let tracked_cat_results = tracked_cat_result_page["query"]["pages"].as_array().ok_or("tracked_cat_results")?;
        for tracked_cat_result in tracked_cat_results {
			let tracked_cat_title = tracked_cat_result["title"].as_str().ok_or("tracked_cat_result.title")?;
			if ends_in_four_digits(tracked_cat_title) {
				// date subcategory, skip because there are too many of these
                continue;
            }

            let never_recurse = never_recurse_list.iter().any(|s| s == tracked_cat_title);
            match size(&api, tracked_cat_title, &tracked_cat_result["categoryinfo"], never_recurse) {
                Ok(num) => { counts.insert(tracked_cat_title["Category:".len()..].to_string(), num); },
                Err(e) => println!("size err: inner {}, res pg {:?}", e, tracked_cat_result_page),
            }
        }
    }

    let mut output_filename = std::path::PathBuf::from(config.get_str("output_directory")?);
    output_filename.push(chrono::Utc::now().format("%d %B %Y").to_string());
    output_filename.set_extension("json");
    std::fs::write(output_filename, serde_json::to_string(&counts)?)?;
    Ok(())
}
