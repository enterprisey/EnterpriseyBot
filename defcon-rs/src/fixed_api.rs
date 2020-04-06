use std::collections::HashMap;
use std::error::Error;

use mediawiki::api::Api;
use serde_json::Value;

fn json_merge(a: &mut Value, b: Value) {
    match (a, b) {
        (a @ &mut Value::Object(_), Value::Object(b)) => match a.as_object_mut() {
            Some(a) => {
                for (k, v) in b {
                    json_merge(a.entry(k).or_insert(Value::Null), v);
                }
            }
            None => {}
        },
        (a @ &mut Value::Array(_), Value::Array(b)) => match a.as_array_mut() {
            Some(a) => {
                for v in b {
                    a.push(v);
                }
            }
            None => {}
        },
        (a, b) => *a = b,
    }
}

fn query_result_count(result: &Value) -> usize {
    match result["query"].as_object() {
        Some(query) => query
            .iter()
            .filter_map(|(_key, part)| match part.as_array() {
                Some(a) => Some(a.len()),
                None => None,
            })
            .next()
            .unwrap_or(0),
        None => 0, // Don't know size
    }
}

/// Same as `get_query_api_json` but automatically loads more results via the `continue` parameter
pub fn get_query_api_json_limit(
    api: &Api,
    params: &HashMap<String, String>,
    max: Option<usize>,
) -> Result<Value, Box<dyn Error>> {
    let mut cont = HashMap::<String, String>::new();
    let mut ret = serde_json::json!({});
    loop {
        let mut params_cont = params.clone();
        for (k, v) in &cont {
            params_cont.insert(k.to_string(), v.to_string());
        }
        let result = api.get_query_api_json(&params_cont)?;
        cont.clear();
        let conti = result["continue"].clone();
        json_merge(&mut ret, result);
        match max {
            Some(m) => {
                if query_result_count(&ret) >= m {
                    break;
                }
            }
            None => {}
        }
        match conti {
            Value::Object(obj) => {
                cont.clear();
                obj.iter().filter(|x| x.0 != "continue").for_each(|x| {
                    let continue_value = x.1.as_str().map_or(x.1.to_string(), |s| s.to_string());
                    cont.insert(x.0.to_string(), continue_value);
                });
            }
            _ => {
                break;
            }
        }
    }
    match ret.as_object_mut() {
        Some(x) => {
            x.remove("continue");
        }
        None => {}
    }

    Ok(ret)
}

