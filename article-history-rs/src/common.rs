use std::{
    borrow::Cow,
    collections::HashMap,
};

use parse_wiki_text::Node;

use crate::Template;

pub fn make_map(params: &[(&str, &str)]) -> HashMap<String, String> {
    params.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
}

pub fn get_template_param_2<'a, 'b>(template: &'a Template, key1: impl Into<Cow<'b, str>>, key2: impl Into<Cow<'b, str>>) -> &'a str {
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

pub fn get_template_param<'a, 'b>(template: &'a Template, key1: impl Into<Cow<'b, str>>) -> &'a str {
    template.named.get(key1.into().as_ref()).map_or("", String::as_ref).trim()
}

pub fn nodes_to_text<'a>(nodes: &[Node<'a>]) -> Result<Cow<'a, str>, String> {
    let error_msg = format!("non-Text node encountered: {:?}", &nodes);
    nodes.iter().map(|node| match node {
        Node::Text { value, .. } => Ok(*value),
        _ => Err(()),
    }).collect::<Result<Vec<_>, _>>().map_or_else(
        |()| Err(error_msg),
        |values| if values.len() == 1 {
            Ok(Cow::Borrowed(values[0]))
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
fn count_existing_entries<'a, T: ToParams<'a>>(history: &Template) -> usize {
    if history.named.contains_key(&format!("{}{}", T::PREFIX, "date")) {
        (2..)
            .into_iter()
            .find(|idx| !history.named.contains_key(&format!("{}{}date", T::PREFIX, idx)))
            .unwrap() // if this doesn't work, then there were an infinite number of parameters!
            - 1 // the find will return the first number WITHOUT an entry,
                // but the numbers are 1-indexed so the count will be 1 less
    } else {
        0
    }
}

pub fn update_article_history<'a, T: ToParams<'a>>(entries: Vec<T>, history: &mut Template) {
    let num_existing_entries = count_existing_entries::<T>(history);

    fn get_param_prefix<'a, T: ToParams<'a>>(idx: usize) -> String {
        match idx {
            0 => T::PREFIX.into(),
            _ => format!("{}{}", T::PREFIX, idx + 1),
        }
    }

    history.named.extend(entries
        .into_iter()
        .map(ToParams::to_params)
        .zip(num_existing_entries..) // i.e. if there are 2 existing entries, the first new index will be 3
        .flat_map(|(params, idx): (T::Iter, usize)| {
            params.map(move |(suffix, value)| (get_param_prefix::<T>(idx) + suffix, value.into_owned()))
        }),
    );
}
