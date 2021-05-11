use std::{
    borrow::Cow,
    iter,
};

use super::OtherTemplate;
use crate::common::{ToParams, try_page_existence, PageExistenceResult};

pub struct DykEntry<'a> {
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

pub async fn parse_dyk_template<'a>(
    api: &mediawiki::api::Api,
    article_title: &str,
    template: &'a OtherTemplate,
) -> Result<DykEntry<'a>, String> {
    let param_2_is_numeric = template.unnamed.get(1).map_or(false, |param_2| param_2.chars().all(char::is_numeric));
    let date: Cow<'_, str> = if param_2_is_numeric {
        Cow::Owned(format!("{} {}", template.unnamed[0], template.unnamed[1]))
    } else {
        Cow::Borrowed(template.unnamed.get(0).ok_or(format!("{}: no first unnamed parameter!", article_title))?)
    };
    let hook = template.named.get("entry").or_else(||
        if param_2_is_numeric {
            template.unnamed.get(2)
        } else {
            template.unnamed.get(1)
        })
        .map(String::as_ref)
        .map(Cow::Borrowed);
    let nompage: Option<Cow<'_, _>> = match template.named.get("nompage") {
        Some(page) => Some(Cow::Borrowed(page.as_ref())),
        None => {
            let content_nom_page = "Template:Did you know nominations/".to_string() + article_title;
            let talk_nom_page = "Template talk:Did you know/".to_string() + article_title;
            match try_page_existence(api, &content_nom_page, &talk_nom_page).await? {
                PageExistenceResult::PrimaryExists => Some(Cow::Owned(content_nom_page)),
                PageExistenceResult::BackupExists => Some(Cow::Owned(talk_nom_page)),
                PageExistenceResult::NeitherExist => None,
            }
        },
    };
    Ok(DykEntry { date, hook, nompage })
}
