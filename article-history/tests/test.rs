use article_history_rs::TemplateNameMap;

fn build_static_template_type_map() -> TemplateNameMap {
    TemplateType::iter()
        .map(|t| (&t.get_template_title()[9..], Either::Right(t)))
        .chain(("Article history", Either::Left(ArticleHistoryTemplateType)))
        .collect()
}
