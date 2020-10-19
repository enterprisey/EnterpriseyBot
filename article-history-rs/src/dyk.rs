use std::{
    borrow::Cow,
    iter,
};

use super::Template;
use crate::common::ToParams;

struct DykEntry<'a> {
    date: Cow<'a, str>,
    hook: Option<Cow<'a, str>>,
    nompage: Option<Cow<'a, str>>,
}

impl<'a> ToParams<'a> for DykEntry<'a> {
    const PREFIX: &'static str = "dyk";
    type Iter = iter::Chain<
        iter::Chain<
            iter::Once<(&'static str, Cow<'a, str>)>,
            std::option::IntoIter<(&'static str, Cow<'a, str>)>,
        >,
        std::option::IntoIter<(&'static str, Cow<'a, str>)>,
    >;

    fn to_params(self) -> Self::Iter {
        let DykEntry { date, hook, nompage } = self;
        iter::once(("date", date))
            .chain(hook.map(|hook| ("entry", hook)).into_iter())
            .chain(nompage.map(|nompage| ("nom", nompage)).into_iter())
    }
}

