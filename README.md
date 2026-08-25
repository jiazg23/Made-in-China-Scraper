# Made-in-China Product & Supplier Scraper (Reverse Image Search)

Search Made-in-China.com by product keyword or product image and get one structured row per unique supplier—not one row per listing. This Apify Actor combines product discovery, reverse-image search, supplier-profile enrichment, pricing, MOQ, audit badges, and source links in a dataset built for sourcing teams, automations, APIs, and AI clients connected through Apify MCP.

Use it for manufacturer discovery, procurement research, supplier shortlisting, private-label sourcing, competitor research, Amazon FBA, Shopify, dropshipping, and B2B lead research.

## New: search Made-in-China from your AI client

This Actor is ready for AI clients that support the Apify MCP server. Users connect their AI to Apify—not directly to this GitHub repository—and can then discover, run, and retrieve results from the Actor with natural-language requests.

### Connect once

For a general Apify MCP connection, add:

```text
https://mcp.apify.com/
```

For a connection limited to this Actor, use:

```text
https://mcp.apify.com/?tools=jzgautomation/made-in-china-supplier-finder
```

Then sign in to Apify, authorize the connection, and ask the AI to use **Made-in-China Product & Supplier Scraper (Reverse Image Search)**.

Clients that use a JSON MCP configuration can use:

```json
{
  "mcpServers": {
    "apify-made-in-china": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://mcp.apify.com/?tools=jzgautomation/made-in-china-supplier-finder",
        "--header",
        "Authorization: Bearer <YOUR_APIFY_API_TOKEN>"
      ]
    }
  }
}
```

### Ask for a keyword search

> Use Apify to run Made-in-China Product & Supplier Scraper for “stainless steel glass shower hinge.” Find 10 unique suppliers and return supplier names, profile URLs, audit status, product links, displayed prices, MOQs, business types, and locations.

### Ask for an image search

> Use Apify to run Made-in-China Product & Supplier Scraper with this public product image URL: https://example.com/product.jpg. Find 10 unique suppliers and return their profile URLs, matching products, displayed prices, MOQs, and audit badges.

The AI sends public image searches through `imageUrls`:

```json
{
  "searchMode": "image",
  "imageUrls": [
    "https://example.com/product.jpg"
  ],
  "maxUniqueSuppliersPerImage": 10,
  "maxPagesImage": 1,
  "useApifyProxy": true,
  "includeSupplierDetails": true
}
```

**Image attachment note:** the Actor can use a public image URL or temporary signed URL. A picture attached directly to a chat works only when that AI client makes the attachment available to MCP as a URL. Users can always upload image files through the Actor's Apify Console form.

### Advanced AI prompt examples

These prompts combine an Actor run with analysis performed by the AI after it retrieves the dataset.

#### Compare several product searches

> Use Apify to run Made-in-China Product & Supplier Scraper for “glass shower hinge,” “stainless steel glass clamp,” and “frameless shower door hardware.” Collect up to 10 unique suppliers per keyword using one page per keyword. Return the raw dataset, then create a comparison table with supplier name, profile URL, matching keyword, product, displayed price, MOQ, location, business type, membership, and audit status. Clearly mark missing values instead of guessing.

#### Build an audited-supplier shortlist

> Search Made-in-China for “CNC machining parts” with a maximum of 25 unique suppliers and two result pages. Include supplier profile details. Shortlist suppliers whose returned records explicitly show `audited_supplier: true`, then compare business type, year established, employee count, location, main products, displayed MOQ, and price. Preserve every source product and supplier URL. Do not treat a membership badge as proof of product quality.

#### Compare suppliers from multiple images

> Run Made-in-China Product & Supplier Scraper for [IMAGE URL 1], [IMAGE URL 2], and [IMAGE URL 3] in one batch. Collect up to 10 suppliers separately for each image, enable Apify Proxy, and save separate CSV files. Identify suppliers appearing in more than one image search and compare their matching products, displayed prices, MOQs, locations, business types, and audit badges.

#### Verify that results match the requested product

> Run Made-in-China Product & Supplier Scraper for “[PRODUCT KEYWORD]” or [PUBLIC IMAGE URL]. Do not assume that Made-in-China's ranking means every result is relevant. Classify each returned listing as **exact match**, **likely variant**, **unrelated**, or **unverified**. Compare the product title, result image, visible attributes, and product page with my original request. Give a short evidence-based reason, exclude unrelated results from the recommended shortlist, and preserve the complete raw Actor dataset separately.

Recommended response columns:

| Column | Meaning |
|---|---|
| `match_status` | Exact match, likely variant, unrelated, or unverified |
| `match_confidence` | High, medium, or low |
| `match_reason` | Specific matching or conflicting product attributes |
| `source_product_url` | Original Made-in-China product link from the Actor |
| `supplier_name` | Supplier name returned by the Actor |
| `supplier_profile_url` | Supplier profile link returned by the Actor |

Made-in-China does not expose a trustworthy image-similarity percentage. The Actor therefore preserves the displayed result image, canonical product URL, rank, and visible attributes so a person or capable AI client can verify each match.

#### Create CSV exports for a sourcing team

> Run a keyword search for “magnetic phone holder” and “foldable phone stand.” Set `saveCsvFile` to `true` and `csvOutputMode` to `both`. Retrieve the supplier dataset and tell me where to download the combined CSV and separate keyword files.

Corresponding input:

```json
{
  "searchMode": "keyword",
  "searchTerms": [
    "magnetic phone holder",
    "foldable phone stand"
  ],
  "maxUniqueSuppliersPerKeyword": 15,
  "maxPagesText": 1,
  "useApifyProxy": true,
  "includeSupplierDetails": true,
  "saveCsvFile": true,
  "csvOutputMode": "both",
  "csvFilename": "made-in-china-phone-accessory-suppliers.csv"
}
```

#### Run a strict diagnostic test

> Test Made-in-China Product & Supplier Scraper with one keyword, one page, and five suppliers. Enable Apify Proxy and set `failOnNoResults` to `true`. If the run fails or returns no rows, retrieve the run log, `RUN_SUMMARY.json`, and any diagnostic HTML, then report the most likely cause.

#### Return integration-ready JSON

> Run Made-in-China Product & Supplier Scraper for “pet grooming brush self cleaning.” Return up to 10 unique suppliers. Preserve the Actor's original field names and return valid JSON only so I can pass the results to another automation.

**Prompting tip:** ask the AI to preserve source URLs, distinguish Made-in-China badges from independent verification, mark unavailable data as missing, and avoid inventing certifications, contact details, prices, or supplier claims.

## What this Actor does

- Searches Made-in-China with one or more product keywords.
- Runs Made-in-China reverse-image search for up to 20 uploaded images or public image URLs.
- Applies supplier limits separately to every keyword or image, so one input cannot stop the remaining searches.
- Returns one row per unique supplier while retaining every matched listing in `matched_products`.
- Extracts product IDs, images, canonical links, prices, normalized price ranges, MOQs, visible attributes, ranks, and Secured Trading indicators.
- Extracts supplier names, profile links, locations, Audited Supplier and Leading Factory badges, membership, ratings, and visible capability labels.
- Optionally visits public supplier profiles for business type, main products, establishment date, employee count, address, membership history, rating, response time, and company description.
- Writes structured records to the default Apify dataset.
- Optionally saves combined and per-search CSV files.
- Saves `RUN_SUMMARY.json` and diagnostic HTML when a search cannot be processed.
- Publishes agent-readable input, output, and dataset schemas for Apify MCP and API clients.

## Why it is different

Many Made-in-China scrapers return one row per product card and support only keywords or URLs. This Actor is designed around supplier discovery:

- **Keyword and reverse-image search** in one Actor.
- **One row per supplier**, with duplicate listings aggregated instead of inflating the result count.
- **Independent limits per input**, including multi-image batches.
- **Supplier profile enrichment** for public company information beyond the result card.
- **MCP-ready schemas and prompts** for AI-assisted sourcing workflows.
- **No browser dependency**, reducing container startup time and memory use.

## Use in Apify Console

1. Choose **Keyword search** or **Image search**.
2. Add product keywords, upload product images, or provide public image URLs.
3. Start with 10 suppliers and one page or result batch per input.
4. Keep **Use Apify Proxy** enabled for more reliable production runs.
5. Leave **Include supplier profile details** enabled when you need company-level fields; disable it for a faster listing-only run.
6. For larger batches, open **Run options** and choose a sufficient **Timeout** or enable **No timeout**.
7. Run the Actor and open **Supplier results** in the Output tab.

### Keyword input

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

`maxUniqueSuppliersPerKeyword` is enforced separately for every keyword. A supplier found for several keywords is returned once and keeps all matching keywords and products.

### Image input

Select **Image search** in the Apify input form and use **Product images** to upload files:

```json
{
  "searchMode": "image",
  "uploadedImages": [
    "uploaded-image-key-1",
    "uploaded-image-key-2"
  ],
  "maxUniqueSuppliersPerImage": 10,
  "maxPagesImage": 1,
  "skipFailedImages": true,
  "useApifyProxy": true
}
```

For MCP or API use, pass public image URLs directly:

```json
{
  "searchMode": "image",
  "imageUrls": [
    "https://example.com/product-one.jpg",
    "https://example.com/product-two.webp"
  ],
  "maxUniqueSuppliersPerImage": 10,
  "maxPagesImage": 1,
  "skipFailedImages": true,
  "useApifyProxy": true
}
```

The combined limit across uploaded files and public URLs is 20 images. Each image is searched separately. URLs must be public HTTP or HTTPS resources and return a supported image no larger than 20 MB. Made-in-China accepts JPG, PNG, and BMP uploads; the Actor automatically converts WebP and GIF inputs to JPEG.

Clear, tightly cropped, product-only images usually produce better results than collages, blurry photos, lifestyle scenes, or screenshots with large text overlays.

## Main input fields

| Field | Purpose | Default |
|---|---|---|
| `searchMode` | `keyword` or `image` | `keyword` |
| `searchTerms` | Product queries used in keyword mode | `[]` — user input required |
| `maxUniqueSuppliersPerKeyword` | Separate supplier cap for each keyword | `10` |
| `maxPagesText` | Result pages processed per keyword | `1` |
| `uploadedImages` | Product images uploaded through Apify Console | `[]` |
| `imageUrls` | Direct public image URLs for image mode | `[]` |
| `maxUniqueSuppliersPerImage` | Separate supplier cap for each image | `10` |
| `maxPagesImage` | Result batches per image; up to 20 listings per batch | `1` |
| `useApifyProxy` | Use Apify Proxy for Made-in-China requests | `true` |
| `includeSupplierDetails` | Visit accepted public supplier profiles for additional company fields | `true` |
| `skipFailedImages` | Continue when one image fails | `true` |
| `failOnNoResults` | Fail rather than warn when the final dataset is empty | `false` |
| `saveCsvFile` | Save CSV files in addition to the dataset | `true` |
| `csvOutputMode` | `combined`, `separate`, or `both` | `combined` |
| `csvFilename` | Combined CSV filename | `made_in_china_results.csv` |

Fields belonging to the unselected search mode are ignored. Keyword mode requires at least one keyword, and image mode requires at least one uploaded image or public image URL. The Actor has no separate internal runtime limit; use Apify's native **Timeout** or **No timeout** setting as the single source of truth.

## Output

Each dataset item represents one unique Made-in-China supplier. The first product match appears in convenient top-level fields, while `matched_products` preserves all distinct listings and source inputs retained for that supplier.

| Field | Description |
|---|---|
| `search_input` | First keyword or resolved image filename that matched the supplier |
| `search_type` | `keyword` or `image` for the first match |
| `matched_search_inputs` | Every keyword or image filename that matched the supplier |
| `name` | First matched product title |
| `product_id` | Made-in-China product identifier |
| `product_url` | Canonical product listing URL |
| `product_image_url` | Primary image displayed on the result card |
| `price` | Displayed price or price range |
| `price_min`, `price_max`, `currency` | Normalized price fields |
| `min_order` | Displayed minimum order quantity |
| `moq_quantity`, `moq_unit` | Normalized MOQ fields |
| `product_attributes` | Visible listing specifications |
| `secured_trading` | Whether the listing shows Secured Trading |
| `is_sponsored` | Whether Made-in-China identifies the result as promoted |
| `match_rank` | One-based result position for the first match |
| `result_page` | Keyword page or image-result batch number |
| `vendor_name` | Supplier company name |
| `vendor_profile_url` | Canonical public supplier profile URL |
| `company_id` | Made-in-China company identifier when available |
| `audited_supplier` | Whether Made-in-China displays the Audited Supplier badge |
| `leading_factory` | Whether Made-in-China displays the Industry-leading Audited Factory badge |
| `member_type`, `member_since` | Displayed Made-in-China membership information |
| `supplier_rating` | Public supplier rating when displayed |
| `supplier_capability_index` | Count of visible capability stars |
| `supplier_from` | Public supplier location |
| `business_type` | Public business type from the listing or supplier profile |
| `main_products` | Public main-products list from the supplier profile |
| `year_established` | Public establishment date or year |
| `employee_count` | Public employee count when displayed |
| `address` | Public company address |
| `average_response_time` | Displayed average response time |
| `supplier_capability_tags` | Visible labels such as ODM Services |
| `company_description` | Public supplier introduction |
| `matched_products` | Every retained product match and its source input |

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

Missing values remain `null`, empty arrays, or `N/A`. The Actor does not invent supplier claims, certifications, contact information, or prices.

## Search behavior and limits

### Keyword mode

Every keyword runs independently through Made-in-China's public product search. The Actor follows numbered result pages until it reaches the configured supplier or page limit.

Use specific queries:

- `stainless steel glass shower hinge`
- `CNC machining aluminum parts`
- `portable solar generator 1000W`
- `pet grooming brush self cleaning`

### Image mode

Every image is downloaded or resolved, normalized when necessary, uploaded to Made-in-China's reverse-image search, and processed separately. One image reaching `maxUniqueSuppliersPerImage` does not stop later images.

Made-in-China currently exposes up to five image-result batches, with up to 20 product cards per batch. The Actor therefore limits `maxPagesImage` to 5.

### Supplier deduplication

Suppliers are deduplicated across the complete run using the supplier profile URL when available, followed by normalized supplier name and then product URL. If the same supplier appears for several keywords or images, it is returned once with every matching source in `matched_search_inputs` and every retained listing in `matched_products`.

### Supplier profile enrichment

When `includeSupplierDetails` is enabled, the Actor visits the public profile of each accepted supplier. This can add business type, location, main products, establishment information, employees, address, membership history, rating, response time, and a public company introduction. Disable it when speed matters more than company-level detail.

## Reliability and troubleshooting

Made-in-China can change its HTML or return traffic challenges. Results may vary by location, proxy, current listings, and current site layout.

For the most reliable runs:

- Keep **Use Apify Proxy** enabled for production and larger batches.
- Test one keyword or image before increasing limits.
- Start with one page or result batch and 10 suppliers per input.
- Use specific product keywords.
- Keep images tightly cropped around one product.
- Use Apify's native **Timeout** or **No timeout** run option for larger batches.
- Review the run log and `RUN_SUMMARY.json` when an input produces no rows.
- Check the key-value store for diagnostic HTML when a page cannot be parsed.

By default, the Actor keeps successful results and finishes with a warning when the final dataset is empty. Enable **Strict failure mode** (`failOnNoResults`) when an automation or MCP workflow should treat an empty run as failed. Enable **Skip failed images** to continue a multi-image batch after one invalid or rejected image.

## CSV exports

The default Apify dataset is always produced and can already be downloaded as JSON, CSV, Excel, XML, and other formats. `saveCsvFile` is enabled by default, so runs also create a named file in the key-value store. Disable it only when the dataset is sufficient and no named CSV file is needed.

- **Combined CSV** — one file containing the complete run.
- **Separate CSV files** — one file per keyword or image.
- **Combined and separate files** — both formats.

Nested arrays and objects are encoded as compact JSON in CSV cells.

## API and automation

Because this is an Apify Actor, it can also be used through:

- Apify API
- Scheduled Actor tasks
- Webhooks
- Make
- Zapier
- Apify MCP-compatible AI clients

The input, output, and dataset schemas provide machine-readable descriptions so API and AI clients can understand search modes, per-input limits, optional enrichment, source attribution, and missing values without guessing from source code.

## Limitations

- Made-in-China may return traffic challenges or temporarily reject image uploads.
- Search ranking and visual similarity are controlled by Made-in-China and can include variants or unrelated products.
- Not every listing or public supplier profile exposes every field.
- Membership and Audited Supplier badges are reported as displayed; they are not an independent endorsement by this Actor.
- Contact details hidden behind login are not collected.
- The Actor does not send inquiries, open chats, log in, or contact suppliers.
- Site layout changes may require parser maintenance.
- Results should be reviewed before purchasing or selecting a supplier.

## Support

For problems or custom requirements, email **jcustombussiness@gmail.com** and include:

- Actor run ID
- Search mode and sanitized input; remove private or signed image URLs
- Expected versus actual behavior
- Relevant log messages or screenshots

## Local development

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m py_compile src/main.py src/parsing.py tests/test_parsing.py tests/test_images.py
docker build -t made-in-china-supplier-finder .
docker run --rm -e ACTOR_STARTUP_CHECK=1 made-in-china-supplier-finder
```

## Responsible use

Use this Actor responsibly and in compliance with Made-in-China's terms of service, applicable laws, and Apify platform policies. It collects information displayed on public product and supplier pages. Respect website access controls, personal-data rules, and reasonable request volumes.
