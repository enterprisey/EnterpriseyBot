use std::{
    borrow::Cow,
    iter,
};

use chrono::NaiveDateTime;

use super::{RevId, Template};
use crate::common::{ToParams, get_template_param, get_template_param_2};

pub enum ItnLink {
    /// Portal:Current events/{{#time:Y F d}}
    PortalSubpage,

    /// Oldid (of Template:In the news)
    ItnOldid(RevId),

    /// Unlinked in {{ITN talk}}.
    /// Linked in {{Article history}}, but we don't care where.
    NoLink,
}

pub struct ItnEntry {
    date: NaiveDateTime,
    link: ItnLink,
}

impl<'a> ToParams<'a> for ItnEntry {
    const PREFIX: &'static str = "itn";
    type Iter = iter::Chain<
        iter::Once<(&'static str, Cow<'a, str>)>,
        std::option::IntoIter<(&'static str, Cow<'a, str>)>,
    >;

    fn to_params(self) -> Self::Iter {
        let ItnEntry { date, link } = self;
        let date_text = date.format("%Y-%m-%d").to_string(); // like 2020-09-21
        let link_text: Option<String> = match link {
            ItnLink::PortalSubpage => Some(format!("Portal:Current events/{}", date.format("%Y %B %d"))),
            ItnLink::ItnOldid(revid) => Some(format!("Special:Permalink/{}", revid)),
            ItnLink::NoLink => None,
        };
        iter::once(("date", Cow::Owned(date_text))).chain(link_text.map(|link_text| ("link", Cow::Owned(link_text))).into_iter())
    }
}

/// Logic taken from:
///  - Template:ITN talk, revid 898412144 by Jonesey95 on 23 May 2019
///  - Template:ITN talk/date, revid 713084449 by MSGJ on 1 April 2016
pub fn parse_itn_template(template: &Template) -> Vec<ItnEntry> {
    let global_alt = !get_template_param(template, "alt").is_empty();

    // First parse item 1
    // I have no clue how this typechecks or borrowchecks
    let date1_owned: Cow<'_, str> = template.named.get("date")
        .map_or(template.named.get("date1")
            .map_or(Cow::Owned(format!("{} {}",
                template.unnamed.get(0).map_or("", |x| &*x),
                template.unnamed.get(1).map_or("", |x| &*x))), |x| Cow::Borrowed(x.as_ref())), |x| Cow::Borrowed(x.as_ref()));
    let date1 = date1_owned.as_ref().trim();
    let entry1: Option<ItnEntry> = if date1.is_empty() {
        None
    } else {
        let oldid1 = get_template_param_2(&template, "oldid1", "oldid");
        let alt1 = global_alt || !get_template_param(&template, "alt1").is_empty();
        Some(ItnEntry {
            date: dtparse::parse(date1).unwrap().0,
            link: match (alt1, oldid1.parse()) {
                (true, _) => ItnLink::PortalSubpage,
                (false, Ok(i)) => ItnLink::ItnOldid(i),
                (false, Err(_)) => ItnLink::NoLink,
            },
        })
    };

    // Then parse the rest of the items
    if template.named.contains_key("date2") {
        (2..=6).into_iter().filter_map(|idx| {
            let date_n = get_template_param(&template, format!("date{}", idx));
            if date_n.is_empty() {
                None
            } else {
                let oldid_n = get_template_param(&template, format!("oldid{}", idx));
                let alt_n = global_alt || !get_template_param(&template, format!("alt{}", idx)).is_empty();
                Some(ItnEntry {
                    date: dtparse::parse(date_n).unwrap().0,
                    link: match (alt_n, oldid_n.parse()) {
                        (true, _) => ItnLink::PortalSubpage,
                        (false, Ok(i)) => ItnLink::ItnOldid(i),
                        (false, Err(_)) => ItnLink::NoLink,
                    },
                })
            }
        }).chain(entry1.into_iter()).collect()
    } else {
        entry1.into_iter().collect()
    }
}

//fn count_existing_itn_items(history: &Template<'_>) -> usize {
//    if history.named.contains_key("itndate") {
//        (2..)
//            .into_iter()
//            .find(|idx| !history.named.contains_key(&format!("itn{}date", idx)))
//            .unwrap() // if this doesn't work, then there were an infinite number of ITN parameters!
//            - 1 // the find will return the first number WITHOUT an entry,
//                // but the numbers are 1-indexed so the count will be 1 less
//    } else {
//        0
//    }
//}
//
///// returns (date parameter value, link parameter value)
//fn itn_entry_to_history_params(entry: &ItnEntry) -> (String, Option<String>) {
//    (
//        entry.date.format("%Y-%m-%d").to_string(), // like 2020-09-21
//        match entry.link {
//            ItnLink::PortalSubpage => Some(format!("Portal:Current events/{}", entry.date.format("%Y %B %d"))),
//            ItnLink::ItnOldid(revid) => Some(format!("Special:Permalink/{}", revid)),
//            ItnLink::NoLink => None,
//        }
//    )
//}
//
//pub fn update_article_history(entries: Vec<ItnEntry>, history: &mut Template<'_>) {
//    let num_existing_itn_items = count_existing_itn_items(history);
//
//    fn get_param_prefix(idx: usize) -> String {
//        match idx {
//            0 => "itn".into(),
//            _ => format!("itn{}", idx),
//        }
//    }
//
//    history.named.extend(entries
//        .iter()
//        .map(itn_entry_to_history_params)
//        .zip(num_existing_itn_items..)
//        .flat_map(|((date_n, link_n), idx)| {
//            iter::once((get_param_prefix(idx) + "date", Cow::Owned(date_n))).chain(
//                link_n
//                    .map(|link_n| (get_param_prefix(idx) + "link", Cow::Owned(link_n)))
//                    .into_iter())
//        })
//    );
//}
