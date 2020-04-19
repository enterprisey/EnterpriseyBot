use std::{
    collections::{HashMap, HashSet},
    convert::TryInto,
    error::Error,
    fmt,
    fs::{File, OpenOptions},
    io::{Read, Write},
    ops::Range,
    path,
};

use chrono::{prelude::*, Duration};
use config;
use lazy_static::lazy_static;
use mediawiki::{
    api::Api,
    page::{Page, PageError},
    title::Title,
};
use regex::Regex;

static ISO_8601_FMT: &str = "%Y-%m-%dT%H:%M:%SZ";
static SUMMARY: &str = "[[Wikipedia:Bots/Requests for approval/EnterpriseyBot 10|Bot]] removing the article class assessment";

lazy_static! {
    static ref REGEX: Regex = Regex::new(r"(?xs) # enable comments, allow . to match \n
        \{\{ # begin template

        # capturing group 1: template name (should start with 'wikiproject', case-insensitive)
        # note the | at the end
        ([Ww][Ii][Kk][Ii][Pp][Rr][Oo][Jj][Ee][Cc][Tt][^\|\}]*?)

        # capturing groups 2-n are the values of the 'class' parameters
        (?:
            # a class parameter
            (\|\s*class\s*=\s*([^\|\}]+?)\s*)
            |
            # maybe some other parameters
            \|[^\|\}]+?
        )+? # must have at least one class parameter

        \}\}").expect("invalid regex");
    static ref NOVELS_WIKIPROJECT_REGEX: Regex = Regex::new("(?i)NovelsWikiProject").expect("invalid regex");
}

fn make_map(params: &[(&str, &str)]) -> HashMap<String, String> {
    params.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
}

#[derive(Debug)]
struct BotError(String);

impl BotError {
    fn new(s: impl Into<String>) -> Self { BotError(s.into()) }
}

impl fmt::Display for BotError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "BotError({})", self.0)
    }
}

impl Error for BotError {}

/// Returns true if the page with the given title was a redirect one week ago.
fn check_redirect_age(api: &Api, title: &Title) -> Result<bool, Box<dyn Error>> {
    let one_week_ago = (Utc::now() - Duration::weeks(1)).format(ISO_8601_FMT).to_string();
    let title = title.full_pretty(api).ok_or(BotError::new("Bad title"))?;
    let res = api.get_query_api_json(&make_map(&[
        ("action", "query"),
        ("prop", "revisions"),
        ("titles", &title),
        ("rvprop", "content"),
        ("rvslots", "main"),
        ("rvlimit", "1"),
        ("rvstart", &one_week_ago),
        ("formatversion", "2"),
    ]))?;
    let page = &res["query"]["pages"][0];
    if page["missing"].as_bool() == Some(true) {
        Err(Box::new(BotError::new(format!("missing page (check_redirect_age), title {}", title))))
    } else if page["revisions"].is_null() {
        Ok(false) // page just didn't exist a week ago
    } else {
        Ok(page["revisions"][0]["slots"]["main"]["content"].as_str()
            .ok_or(BotError::new(format!("bad API response (check_redirect_age): {:?}", res)))?
            .to_ascii_lowercase()
            .contains("#redirect"))
    }
}

/// Gets a list of all templates that redirect to the given set of templates.
/// The inputs should be WITH namespaces; the outputs will be WITHOUT namespaces.
fn get_template_redirects(api: &Api, templates: Vec<String>) -> Result<Vec<String>, Box<dyn Error>> {
    let res = api.get_query_api_json_all(&make_map(&[
        ("action", "query"),
        ("prop", "linkshere"),
        ("titles", &templates.join("|")),
        ("lhprop", "title"),
        ("lhnamespace", /* template */ "10"),
        ("lhshow", "redirect"),
        ("lhlimit", "max"),
        ("formatversion", "2"),
    ]))?;
    res["query"]["pages"].as_array()
       .ok_or(BotError::new(format!("bad API response (get_template_redirects): {:?}", res)))?
       .iter()
       .map(|page| page["linkshere"].as_array()
           .ok_or(BotError::new(format!("bad API response (get_template_redirects): {:?}", res)))
           .map(|linkshere| linkshere
               .iter()
               .map(|val| val["title"].as_str().expect("not a string?")[("template:".len())..].to_ascii_lowercase())
               .collect::<HashSet<_>>().into_iter())).collect::<Result<Vec<_>, _>>()
       .map(|pages| pages.into_iter().flatten().collect())
       .map_err(|e| Box::new(e) as Box<dyn Error>)
}

fn load_progress(filename: &str) -> Result<Option<String>, Box<dyn Error>> {
    if path::Path::new(filename).exists() {
        let mut file = File::open(&filename)?;
        let mut contents = String::new();
        file.read_to_string(&mut contents)?;
        Ok(Some(contents))
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

pub fn process_text(mut text: String, banned_templates: &Vec<String>) -> String {
    #[derive(Debug)]
    enum Edit { Insert(usize, String), Delete(Range<usize>) };
    use Edit::*;
    let mut edits: Vec<Edit> = Vec::new();

    let mut offset = 0;
    let mut locs = REGEX.capture_locations();
    while let Some(_) = REGEX.captures_read_at(&mut locs, &text, offset) {
        //println!("{} groups {}", line!(), (0..2 * locs.len()).map(|idx| locs.get(idx).map(|(start, end)| &text[start..end]).unwrap_or("None")).collect::<Vec<_>>().join(","));
        //println!("{} whole match {}", line!(), &text[locs.get(0).unwrap().0..locs.get(0).unwrap().1]);

        let mut template_name = (&text[locs.get(1).unwrap().0..locs.get(1).unwrap().1]).to_string();

        // Increment the offset to ensure that we keep progressing through the string
        let new_offset = locs.get(1).unwrap().1;
        if new_offset > offset {
            offset = new_offset;
        } else {
            panic!("no progress being made!");
        }

        // Check if template is one of the banned templates
        template_name.make_ascii_lowercase();
        if banned_templates.iter().any(|b| b == &template_name) {
            //println!("banned; continuing");
            continue;
        }

        if locs.get(2).is_none() {
            continue;
        }

        if let Some((start, end)) = locs.get(3) {
            if (&text[start..end]).trim().is_empty() {
                continue;
            }
        }

        // Schedule edits deleting the class params
        let num_class_params = (locs.len() - 2) / 2;
        for class_param_idx in 0..num_class_params {
            let capturing_group_idx = class_param_idx * 2 + 2;
            edits.push(Delete(locs.get(capturing_group_idx).unwrap().0..locs.get(capturing_group_idx).unwrap().1));
        }

        // Schedule an edit inserting the former class param
        let former = format!("<!-- Formerly assessed as {} -->",
            (0..num_class_params)
                .map(|class_param_idx| {
                    let capturing_group_idx = class_param_idx * 2 + 3;
                    format!("{}{}", &text[locs.get(capturing_group_idx).unwrap().0..locs.get(capturing_group_idx).unwrap().1], "-class")
                })
                .collect::<Vec<String>>()
                .join(", "));
        let idx_of_template_end = locs.get(0).unwrap().1;
        edits.push(Insert(idx_of_template_end, former));
    }

    // Make edits
    for edit in edits.into_iter().rev() {
        match edit {
            Insert(idx, insert_text) => text.insert_str(idx, &insert_text),
            Delete(range) => text.replace_range(range, ""),
        }
    }
    text
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut config = config::Config::default();
    config
        .merge(config::File::with_name("settings"))?
        .merge(config::Environment::with_prefix("APP"))?;
    let username = config.get_str("username")?;
    let password = config.get_str("password")?;

    let num_edits_per_session: usize = config.get_int("edits_per_session")?.try_into()?;
    let progress_filename = config.get_str("progress_file")?;

    let mut api = Api::new("https://en.wikipedia.org/w/api.php")?;
    api.login(username, password)?;

    api.set_user_agent(format!("EnterpriseyBot/redirect-banners-rs/{} (https://en.wikipedia.org/wiki/User:EnterpriseyBot; apersonwiki@gmail.com)", env!("CARGO_PKG_VERSION")));

    let mut params = make_map(&[
        ("action", "query"),
        ("list", "allpages"),
        ("apnamespace", /* article */ "0"),
        ("apfilterredir", "redirects"),
        ("aplimit", "500"),
    ]);
    if let Some(starting_title) = load_progress(&progress_filename)? {
        params.insert("apfrom".to_string(), starting_title.trim().to_string());
    }

    let base_banned_templates = config.get_array("banned_templates")?
        .into_iter().map(|val| val.into_str().map(|val| format!("Template:{}", val))).collect::<Result<_, _>>()?;
    let banned_templates = get_template_redirects(&api, base_banned_templates)?;

    let mut edit_list: Vec<(Title, String)> = Vec::new(); // (title, new text)
    'main_loop: for each_result_set in api.get_query_api_json_limit_iter(&params, None) {
        let each_result_set = each_result_set?;
        let pages = each_result_set["query"]["allpages"].as_array()
            .ok_or(BotError::new(format!("bad API result: {:?}", each_result_set)))?;
        for each_page_obj in pages {
            let mut title = Title::new(each_page_obj["title"].as_str()
                .ok_or(BotError::new(format!("bad API result (title construction): {:?}", each_result_set)))?,
                /* article */ 0);
            if !check_redirect_age(&api, &title)? {
                continue;
            }

            title.toggle_talk();
            let page = Page::new(title);
            match page.text(&api) {
                Ok(text) => {
                    let text = NOVELS_WIKIPROJECT_REGEX.replace(&text, "WikiProject Novels").to_string();
                    let new_text = process_text(text.clone(), &banned_templates);
                    if new_text != text {
                        edit_list.push((page.title().clone(), new_text));
                        println!("WILL EDIT {:?}", page.title());
                        if edit_list.len() >= num_edits_per_session {
                            break 'main_loop;
                        }
                    }
                },
                Err(PageError::Missing(_)) => continue,
                Err(e) => return Err(Box::new(e)),
            };
        }
    }

    if let Some((title, _)) = edit_list.get(edit_list.len().saturating_sub(1)) {
        save_progress(progress_filename, title.pretty().to_string())?;
    }

    for (title, new_text) in edit_list.into_iter() {
        Page::new(title).edit_text(&mut api, new_text, SUMMARY)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_unchanged(text: impl Into<String>, banned: &Vec<String>) {
        let text = text.into();
        assert_eq!(process_text(text.clone(), banned), text);
    }

    #[test]
    fn test_process_text() {
        assert_unchanged("{{WikiProject X|importance=}}", &vec![]);
        assert_unchanged("{{WikiProject X|class=|importance=}}", &vec![]);
        assert_unchanged("{{WikiProject X|class= |importance=}}", &vec![]);
        assert_eq!(process_text("{{Wikiproject Cars|class=Foo}}".to_string(), &vec![]),
            "{{Wikiproject Cars}}<!-- Formerly assessed as Foo-class -->");
        assert_eq!(process_text("{{Wikiproject Cars|a|class=Foo}}".to_string(), &vec![]),
            "{{Wikiproject Cars|a}}<!-- Formerly assessed as Foo-class -->");
        assert_eq!(process_text("{{Wikiproject Cars|class=Foo|a}}".to_string(), &vec![]),
            "{{Wikiproject Cars|a}}<!-- Formerly assessed as Foo-class -->");
        assert_eq!(process_text("{{Wikiproject Cars|a|class=Foo|b}}".to_string(), &vec![]),
            "{{Wikiproject Cars|a|b}}<!-- Formerly assessed as Foo-class -->");
    }

    #[test]
    fn test_process_text_more() {
        assert_unchanged("{{WikiProject Astronomy|object=yes|importance=|class=}}\n{{WikiProject Solar System|class=|importance=}}", &vec![]);
    }

    #[test]
    fn test_process_text_wpbs() {
        assert_eq!(process_text("{{WikiProject banner shell|1=
{{WikiProject New York City |class=redirect |importance=NA}}
{{WikiProject Streetcars |NYPT=yes |class=NA |importance=NA}}
}}".to_string(), &vec!["wikiproject banner shell".to_string()]),
            "{{WikiProject banner shell|1=
{{WikiProject New York City |importance=NA}}<!-- Formerly assessed as redirect-class -->
{{WikiProject Streetcars |NYPT=yes |importance=NA}}<!-- Formerly assessed as NA-class -->
}}");
        assert_eq!(process_text("{{Talk header}}
{{WikiProject banner shell|1=
{{WikiProject New York City |class=redirect |importance=NA}}
{{WikiProject Streetcars |NYPT=yes |class=NA |importance=NA}}
{{WikiProject Buses |NYPT=yes |class=redirect |importance=NA}}
}}
".to_string(), &vec!["wikiproject banner shell".to_string()]),
            "{{Talk header}}
{{WikiProject banner shell|1=
{{WikiProject New York City |importance=NA}}<!-- Formerly assessed as redirect-class -->
{{WikiProject Streetcars |NYPT=yes |importance=NA}}<!-- Formerly assessed as NA-class -->
{{WikiProject Buses |NYPT=yes |importance=NA}}<!-- Formerly assessed as redirect-class -->
}}
");
    }
}
