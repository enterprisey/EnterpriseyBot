use std::{
    borrow::Cow,
    collections::HashMap,
};

use parse_wiki_text::{Configuration, Node, Parameter};

mod common;
mod dyk;
mod itn;
mod otd;

const SUMMARY: &str = "[[Wikipedia:Bots/Requests for approval/APersonBot 7|Bot]] merging redundant talk page banners into [[Template:Article history]].";

// as of MW 1.35, the revision table has rev_id as a int(10) unsigned
type RevId = u32;

pub struct Template<'a> {
    name: Cow<'a, str>,
    unnamed: Vec<Cow<'a, str>>,
    named: HashMap<String, Cow<'a, str>>,
}

fn wikitext_to_template_list<'a>(wikitext: &'a str, page_name: &str) -> Vec<Template<'a>> {
    let output = Configuration::default().parse(wikitext);
    assert!(output.warnings.is_empty(), "{:?}", output);
    output
        .nodes
        .into_iter()
        .filter_map(|node| match node {
            Node::Template {
                name: name_nodes,
                parameters,
                ..
            } => {
                let template_name = common::nodes_to_text(&name_nodes).unwrap_or_else(|e|
                    panic!(
                        "while handling '{}': nodes_to_text failed on template name: {}",
                        page_name, e
                    ));
                let (named, unnamed): (Vec<_>, Vec<_>) = parameters
                    .iter()
                    .enumerate()
                    .map(|(param_idx, Parameter { name: name_nodes, value: value_nodes, .. })| {
                        let param_name = name_nodes.as_ref().map(|name_nodes| common::nodes_to_text(&name_nodes)
                            .unwrap_or_else(|e| panic!(
                                "while handling page '{}', template '{}': nodes_to_text failed on the name of parameter index {}: {}",
                                page_name, template_name, param_idx, e
                            )));
                        let param_value = common::nodes_to_text(&value_nodes)
                            .unwrap_or_else(|e| panic!(
                                "while handling page '{}', template '{}': nodes_to_text failed on the value for parameter '{:?}' (index {}): {}",
                                page_name, template_name, param_name, param_idx, e
                            ));
                        (param_name, param_value)
                    }).partition(|(name, _value)| name.is_some());
                let named = named.into_iter().map(|(name, value)| (name.unwrap().into_owned(), value)).collect();
                let unnamed = unnamed.into_iter().map(|(_name, value)| value).collect();
                Some(Template {
                    name: template_name,
                    unnamed,
                    named,
                })
            },
            _ => None,
        })
        .collect()
}

fn main() {
    println!("Hello, world!");
}
