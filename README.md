# analytics-query-analyzer

Analytics Query Analyzer

## Install

```bash
pip install analytics-query-analyzer
```

## Usage

```python
from analytics_query_analyzer import analyze

schema = {
    "production": {
        "shop": {
            "orders": {
                "id": "int64",
                "ordered_at": "datetime",
                "user_id": "int64",
                "payment_amount": "int64",
                "payment_method": "string",
            }
        }
    }
}

references = analyze("select user_id from shop.orders", schema, "production")
print(references)  # {'production.shop.orders': {'user_id'}}
```
