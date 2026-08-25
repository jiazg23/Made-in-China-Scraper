# Made-in-China Product & Supplier Finder

Find Made-in-China products and unique suppliers from product keywords, uploaded images, or public image URLs. The Actor returns one structured row per supplier while preserving every product and search input that matched that supplier.

The input layout intentionally matches the Alibaba Product & Supplier Finder so both Actors are easy to use together.

## What it does

- Searches Made-in-China with up to 20 product keywords.
- Runs reverse-image searches for up to 20 uploaded images or public image URLs.
- Applies supplier limits separately to every keyword or image.
- Aggregates duplicate listings into one row per supplier.
- Preserves all matches in `matched_products` and all source inputs in `matched_search_inputs`.
- Extracts product names, IDs, images, prices, MOQs, visible attributes, and source links.
- Extracts Audited Supplier, Leading Factory, membership, rating, location, business type, and capability labels when displayed.
- Optionally visits accepted public supplier profiles for additional company details.
- Produces Apify datasets plus optional combined or per-input CSV files.
- Saves `RUN_SUMMARY.json` and diagnostic HTML when a page cannot be parsed.

## Search modes

### Keyword search

```json
{
  "searchMode": "keyword",
  "searchTerms": [
    "glass shower hinge",
    "stainless steel glass clamp"
  ],
  "maxUniqueSuppliersPerKeyword": 10,
  "maxPagesText": 1,
  "useApifyProxy": true,
  "includeSupplierDetails": true
}
```

`maxUniqueSuppliersPerKeyword` is enforced separately for every keyword. A supplier that appears for multiple keywords is returned once and keeps all matching keywords and products.

### Image search with public URLs

```json
{
  "searchMode": "image",
  "imageUrls": [
    "https://example.com/product-one.jpg",
    "https://example.com/product-two.jpg"
  ],
  "maxUniqueSuppliersPerImage": 10,
  "maxPagesImage": 1,
  "skipFailedImages": true,
  "useApifyProxy": true
}
```

Each image is downloaded, validated, uploaded to Made-in-China's image search, and processed independently. WebP and GIF input is converted automatically to a supported upload format. One image reaching its supplier limit does not stop later images.

Uploaded images can also be selected directly in Apify Console through the **Product images** field.

## Main input fields

| Field | Purpose | Default |
| --- | --- | --- |
| `searchMode` | `keyword` or `image` | `keyword` |
| `searchTerms` | Product queries used in keyword mode | `glass shower hinge` |
| `maxUniqueSuppliersPerKeyword` | Separate supplier cap for each keyword | `10` |
| `maxPagesText` | Result pages processed per keyword | `1` |
| `uploadedImages` | Images uploaded through Apify Console | `[]` |
| `imageUrls` | Direct public image URLs | `[]` |
| `maxUniqueSuppliersPerImage` | Separate supplier cap for each image | `10` |
| `maxPagesImage` | Image-result batches per image; each contains up to 20 products | `1` |
| `useApifyProxy` | Use Apify Proxy for Made-in-China requests | `true` |
| `includeSupplierDetails` | Visit accepted supplier profiles for additional public company fields | `true` |
| `skipFailedImages` | Continue when one image fails | `true` |
| `failOnNoResults` | Fail rather than warn when the final dataset is empty | `false` |
| `saveCsvFile` | Save CSV files in addition to the dataset | `false` |
| `csvOutputMode` | `combined`, `separate`, or `both` | `combined` |
| `csvFilename` | Combined CSV filename | `made_in_china_results.csv` |

The Actor has no separate internal runtime limit. Use Apify's native run **Timeout** or **No timeout** setting when you need to control run duration.

## Output model

Each dataset row represents one unique supplier. The first match is copied to convenient top-level product fields, and every match is retained inside `matched_products`.

Important product fields include:

- `name`
- `product_id`
- `product_url`
- `product_image_url`
- `price`, `price_min`, `price_max`, `currency`
- `min_order`, `moq_quantity`, `moq_unit`
- `product_attributes`
- `secured_trading`
- `is_sponsored`
- `match_rank`
- `result_page`

Important supplier fields include:

- `vendor_name`
- `vendor_profile_url`
- `company_id`
- `audited_supplier`
- `leading_factory`
- `member_type`, `member_since`
- `supplier_rating`, `supplier_capability_index`
- `supplier_from`
- `business_type`
- `main_products`
- `year_established`
- `employee_count`
- `address`
- `average_response_time`
- `supplier_capability_tags`
- `company_description`

Example:

```json
{
  "search_input": "glass shower hinge",
  "search_type": "keyword",
  "matched_search_inputs": ["glass shower hinge"],
  "name": "Stainless Steel Glass Shower Hinge",
  "product_id": "AbCdEfGhIjKl",
  "product_url": "https://supplier.en.made-in-china.com/product/AbCdEfGhIjKl/example.html",
  "product_image_url": "https://image.made-in-china.com/example.jpg",
  "price": "US$2.83-5.13",
  "price_min": 2.83,
  "price_max": 5.13,
  "currency": "USD",
  "min_order": "60 Pieces",
  "moq_quantity": 60,
  "moq_unit": "Pieces",
  "vendor_name": "Example Hardware Co., Ltd.",
  "vendor_profile_url": "https://supplier.en.made-in-china.com",
  "audited_supplier": true,
  "member_type": "Diamond Member",
  "supplier_from": "Guangdong, China",
  "business_type": "Manufacturer/Factory",
  "matched_products": [
    {
      "search_input": "glass shower hinge",
      "search_type": "keyword",
      "product_id": "AbCdEfGhIjKl",
      "name": "Stainless Steel Glass Shower Hinge",
      "product_url": "https://supplier.en.made-in-china.com/product/AbCdEfGhIjKl/example.html",
      "price": "US$2.83-5.13",
      "min_order": "60 Pieces",
      "match_rank": 1,
      "result_page": 1
    }
  ]
}
```

Missing values remain `null`, empty arrays, or `N/A`; the Actor does not invent supplier claims or prices.

## CSV exports

The Apify dataset is always produced. Enable `saveCsvFile` if you also need files in the key-value store.

- `combined`: one CSV containing the complete run.
- `separate`: one CSV for each keyword or image, with `matched_products` filtered to that input.
- `both`: save combined and separate files.

Nested arrays and objects are encoded as compact JSON in CSV cells.

## MCP and API use

The Actor's input and output schemas are designed for Apify API calls, tasks, automations, and MCP-connected AI clients.

Example AI request:

> Run Made-in-China Product & Supplier Finder for “stainless steel shower hinge.” Find 10 unique suppliers and return supplier names, profile links, audit status, prices, MOQs, business types, locations, and matching product links. Mark missing fields instead of guessing.

Example image request:

> Run Made-in-China Product & Supplier Finder with these three public product image URLs. Find up to 10 unique suppliers for each image, preserve the source filename for every match, and identify suppliers appearing in more than one image search.

## Reliability and diagnostics

Made-in-China can change its HTML or return traffic challenges. For better reliability:

- Keep `useApifyProxy` enabled for production runs.
- Start with one page or image batch and a small supplier limit.
- Use specific product keywords.
- Use direct public image files rather than webpage URLs.
- Review `RUN_SUMMARY.json` and any `*_debug.html` files if an input produces no rows.

The implementation uses Made-in-China's public server-rendered search pages and image-upload flow. It does not require Chrome, which reduces startup time and memory use.

## Local development

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m py_compile src/main.py src/parsing.py
docker build -t made-in-china-supplier-finder .
docker run --rm -e ACTOR_STARTUP_CHECK=1 made-in-china-supplier-finder
```

## Responsible use

Use this Actor in compliance with Made-in-China's terms, applicable laws, and Apify platform policies. It collects fields displayed on public product and company pages. Respect website access controls, personal-data requirements, and reasonable request volumes.
