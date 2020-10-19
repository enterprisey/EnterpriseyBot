use std::{
    borrow::Cow,
    iter,
};

use super::Template;
use crate::common::ToParams;

struct OtdEntry<'a> {
    date: Option<Cow<'a, str>>,
    oldid: Option<Cow<'a, str>>,
}

impl<'a> ToParams<'a> for OtdEntry<'a> {
    const PREFIX: &'static str = "otd";
    type Iter = iter::Chain<
        std::option::IntoIter<(&'static str, Cow<'a, str>)>,
        std::option::IntoIter<(&'static str, Cow<'a, str>)>,
    >;

    fn to_params(self) -> Self::Iter {
        let OtdEntry { date, oldid } = self;
        date.map(|date| ("date", date))
            .into_iter()
            .chain(oldid.map(|oldid| ("oldid", oldid)).into_iter())
    }
}

fn parse_otd_template<'a>(template: &'a Template) -> Vec<OtdEntry<'a>> {
    (1..)
        .into_iter()
        .map(|idx| (idx, format!("oldid{}", idx)))
        .take_while(|(_idx, oldid_name)| template.named.get(oldid_name).is_some())
        .map(|(idx, oldid_name)| OtdEntry {
            date: template.named.get(&format!("date{}", idx)).map(|x| Cow::Borrowed(x.as_ref())),
            oldid: template.named.get(&oldid_name).map(|x| Cow::Borrowed(x.as_ref())),
        })
        .collect()
}
