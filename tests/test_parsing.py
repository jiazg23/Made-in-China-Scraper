import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from parsing import (  # noqa: E402
    apply_supplier_details,
    canonicalize_mic_url,
    initialize_supplier_record,
    key_for_dedupe,
    merge_supplier_record,
    normalize_image_reference,
    parse_image_search_html,
    parse_moq_details,
    parse_price_details,
    parse_supplier_profile_html,
    parse_text_search_html,
    parse_total_count,
    parse_tracking,
    upsert_supplier_record,
)


TEXT_RESULTS_HTML = """
<div class="search-list">
  <div class="list-node">
    <div class="prod-content">
      <div class="prod-info">
        <b class="trade-icon-holder" data-icon-alt="Secured Trading Service"></b>
        <h2 class="product-name">
          <a href="https://sample.en.made-in-china.com/product/AbCdEfGhIjKl/China-Glass-Shower-Hinge.html?tracking=1"
             ads-data="aid:,ads_srv_tp:,pdid:AbCdEfGhIjKl,pcid:CompanyABC,a:1">
            Stainless Steel Glass Shower Hinge
          </a>
        </h2>
        <a class="product-detail">
          <div class="product-property">
            <div class="info price-info"><strong class="price">US$<span>2.83</span>-<span>5.13</span></strong></div>
            <div class="info">60 Pieces <span>(MOQ)</span></div>
          </div>
          <ul class="property-list">
            <li>Material: <span class="property-val">Stainless Steel</span></li>
            <li>Glass Thickness: <span class="property-val">8-12mm</span></li>
          </ul>
        </a>
        <ul class="company-info">
          <li>
            <a class="compnay-name J-compnay-name" href="//sample.en.made-in-china.com">
              <span>Sample Hardware Co., Ltd.</span>
            </a>
            <div class="company-name-popup">
              <div class="company-tag"><div class="tag-list">Manufacturer/Factory</div></div>
              <li class="cs-level-info"><img alt="Diamond Member"></li>
              <li class="company-address-info">
                Rating: <a class="rate">4.8/5</a>
                <div class="tip"><p class="tip-para">Guangdong, China</p></div>
              </li>
              <div class="verified-list">
                <span class="verified-item">ODM Services<div class="tip">Long explanation</div></span>
              </div>
            </div>
            <div class="leading-factory-container"><img alt="Industry-leading Audited Factory"></div>
            <li class="auth-icon-list">
              <img alt="Audited Supplier">
              <span class="auth-icon-item icon-star"><img><img><img><img><img></span>
            </li>
          </li>
        </ul>
      </div>
      <div class="prod-img"><img data-original="//image.made-in-china.com/sample-product.jpg"></div>
    </div>
  </div>
</div>
<div class="pager"><span class="current">1</span><a href="/productdirectory.do?page=2">2</a></div>
"""


IMAGE_RESULTS_HTML = """
<input type="hidden" name="totalCount" value="82">
<div class="products-item">
  <div class="prod-img"><img data-original="https://image.made-in-china.com/image-result.jpg"></div>
  <div class="detail">
    <div class="secured-trading-icon"></div>
    <div class="product-name">
      <a title="Glass Door Patch Fitting"
         href="https://image-supplier.en.made-in-china.com/product/ZyXwVuTsRqPo/China-Glass-Door-Patch-Fitting.html"
         ads-data="aid:,ads_srv_tp:ad_enhance,pdid:ZyXwVuTsRqPo,pcid:ImageCompany,a:1">
        Glass Door Patch Fitting
      </a>
    </div>
    <a class="product-property">
      <div class="attr-item"><strong class="price">US$<span>2.30</span>-<span>2.75</span></strong></div>
      <div class="attr-item">100 Pieces<span>(MOQ)</span></div>
    </a>
    <div class="company-info">
      <div class="company-name">
        <a class="compnay-name" href="https://image-supplier.en.made-in-china.com">
          <span title="Image Supplier Co., Ltd.">Image Supplier Co., Ltd.</span>
        </a>
      </div>
      <div class="auth-list"><img alt="Gold Member"><img alt="Audited Supplier"></div>
    </div>
  </div>
</div>
"""


SUPPLIER_PROFILE_HTML = """
<div class="sr-comInfo">
  <div class="sr-comInfo-title"><h1>Image Supplier Co., Ltd.</h1></div>
  <div class="sr-comInfo-details">
    <div class="detail-address">Guangdong, China</div>
    <div class="info-item"><div class="info-label">Business Type:</div><div class="info-fields">Manufacturer/Factory &amp; Trading Company</div></div>
    <div class="info-item"><div class="info-label">Main Products:</div><div class="info-fields"><a>Glass Hardware</a><a>Door Hinge</a></div></div>
    <div class="info-item"><div class="info-label">Year of Establishment:</div><div class="info-fields">2022-06-07</div></div>
    <div class="info-item"><div class="info-label">Number of Employees:</div><div class="info-fields">120</div></div>
    <div class="info-item"><div class="info-label">Address:</div><div class="info-fields">Factory Road, Guangdong, China</div></div>
    <div class="review-scores"><div class="score-item-rating">Rating: <a>5.0/5</a></div></div>
    <div class="average-response-time"><span class="response-time-data">≤3.85h</span></div>
    <p class="detail-intro">A public company description.</p>
  </div>
  <div class="sr-comInfo-sign">
    <div id="member-since"><span class="sign-item-text">Gold Member</span><span class="txt-year">Since 2016</span></div>
    <img alt="Audited Supplier">
    <span class="icon-star"><img><img></span>
  </div>
  <a href="https://www.made-in-china.com/sendInquiry/shrom_ImageCompany_ImageCompany.html">Inquiry</a>
</div>
"""


class ParsingTests(unittest.TestCase):
    def test_normalizes_markdown_wrapped_image_references(self):
        url = "https://example.com/product.jpg"
        self.assertEqual(normalize_image_reference(url), url)
        self.assertEqual(normalize_image_reference(f"[{url}]({url})"), url)
        self.assertEqual(normalize_image_reference(f"![product]({url})"), url)

    def test_canonicalizes_made_in_china_urls(self):
        self.assertEqual(
            canonicalize_mic_url("//sample.en.made-in-china.com/product/AbCdEfGhIjKl/Test.html?from=search#top"),
            "https://sample.en.made-in-china.com/product/AbCdEfGhIjKl/Test.html",
        )

    def test_parses_price_moq_and_tracking(self):
        self.assertEqual(
            parse_price_details("US$2.30-2.75"),
            {"price_min": 2.3, "price_max": 2.75, "currency": "USD"},
        )
        self.assertEqual(
            parse_moq_details("100 Pieces (MOQ)"),
            {"moq_quantity": 100, "moq_unit": "Pieces"},
        )
        self.assertEqual(
            parse_tracking("aid:,ads_srv_tp:ad_enhance,pdid:AbCdEfGhIjKl,pcid:CompanyABC"),
            {"product_id": "AbCdEfGhIjKl", "company_id": "CompanyABC", "is_sponsored": True},
        )

    def test_parses_keyword_search_card(self):
        rows = parse_text_search_html(TEXT_RESULTS_HTML, result_page=2, rank_offset=30)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["product_id"], "AbCdEfGhIjKl")
        self.assertEqual(row["company_id"], "CompanyABC")
        self.assertEqual(row["name"], "Stainless Steel Glass Shower Hinge")
        self.assertEqual(row["price_min"], 2.83)
        self.assertEqual(row["moq_quantity"], 60)
        self.assertEqual(row["vendor_name"], "Sample Hardware Co., Ltd.")
        self.assertEqual(row["supplier_from"], "Guangdong, China")
        self.assertEqual(row["business_type"], "Manufacturer/Factory")
        self.assertEqual(row["member_type"], "Diamond Member")
        self.assertEqual(row["supplier_rating"], 4.8)
        self.assertTrue(row["audited_supplier"])
        self.assertTrue(row["leading_factory"])
        self.assertTrue(row["secured_trading"])
        self.assertEqual(row["match_rank"], 31)
        self.assertEqual(row["result_page"], 2)
        self.assertEqual(row["product_attributes"]["Material"], "Stainless Steel")
        self.assertEqual(row["supplier_capability_tags"], ["ODM Services"])

    def test_parses_image_search_card_and_total(self):
        rows = parse_image_search_html(IMAGE_RESULTS_HTML)
        self.assertEqual(parse_total_count(IMAGE_RESULTS_HTML), 82)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["product_id"], "ZyXwVuTsRqPo")
        self.assertEqual(row["company_id"], "ImageCompany")
        self.assertEqual(row["vendor_name"], "Image Supplier Co., Ltd.")
        self.assertEqual(row["member_type"], "Gold Member")
        self.assertEqual(row["moq_quantity"], 100)
        self.assertTrue(row["audited_supplier"])
        self.assertTrue(row["is_sponsored"])

    def test_parses_and_applies_supplier_profile(self):
        details = parse_supplier_profile_html(SUPPLIER_PROFILE_HTML)
        self.assertEqual(details["business_type"], "Manufacturer/Factory & Trading Company")
        self.assertEqual(details["main_products"], ["Glass Hardware", "Door Hinge"])
        self.assertEqual(details["member_since"], 2016)
        self.assertEqual(details["year_established"], "2022-06-07")
        self.assertEqual(details["employee_count"], 120)
        self.assertEqual(details["supplier_rating"], 5.0)
        self.assertEqual(details["average_response_time"], "≤3.85h")
        self.assertEqual(details["company_id"], "ImageCompany")

        row = {"supplier_from": "N/A", "main_products": [], "audited_supplier": False}
        apply_supplier_details(row, details)
        self.assertEqual(row["supplier_from"], "Guangdong, China")
        self.assertEqual(row["main_products"], ["Glass Hardware", "Door Hinge"])
        self.assertTrue(row["audited_supplier"])

    def test_aggregates_products_and_keeps_per_input_limits_separate(self):
        first = {
            "product_id": "FirstProduct",
            "name": "First product",
            "product_url": "https://sample.en.made-in-china.com/product/FirstProduct/Product.html",
            "vendor_name": "Sample Hardware Co., Ltd.",
            "vendor_profile_url": "https://sample.en.made-in-china.com",
            "audited_supplier": False,
        }
        second = {
            "product_id": "SecondProduct",
            "name": "Second product",
            "product_url": "https://sample.en.made-in-china.com/product/SecondProduct/Product.html",
            "vendor_name": "Sample Hardware Co., Ltd.",
            "vendor_profile_url": "https://sample.en.made-in-china.com",
            "audited_supplier": True,
        }

        result = initialize_supplier_record(first, "hinge", "keyword")
        self.assertTrue(merge_supplier_record(result, second, "image.jpg", "image"))
        self.assertEqual(result["matched_search_inputs"], ["hinge", "image.jpg"])
        self.assertEqual([item["product_id"] for item in result["matched_products"]], ["FirstProduct", "SecondProduct"])
        self.assertTrue(result["audited_supplier"])

        suppliers = {}
        first_seen: set[str] = set()
        second_seen: set[str] = set()
        key = key_for_dedupe(first["vendor_name"], first["vendor_profile_url"])
        _, added = upsert_supplier_record(suppliers, first_seen, key, first, "first.jpg", "image", 1)
        self.assertTrue(added)
        _, added = upsert_supplier_record(suppliers, second_seen, key, second, "second.jpg", "image", 1)
        self.assertFalse(added)
        self.assertEqual(first_seen, {key})
        self.assertEqual(second_seen, {key})
        self.assertEqual(suppliers[key]["matched_search_inputs"], ["first.jpg", "second.jpg"])


if __name__ == "__main__":
    unittest.main()
