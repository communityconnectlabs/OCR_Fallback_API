"""
Core analysis logic: sends preprocessed images to Claude and parses the JSON
nutrition response.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

import anthropic

from .imaging import build_image_block

MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 2048

SYSTEM_PROMPT = """
You are a nutrition data extraction expert. Extract nutrition facts AND ingredients from food product images.

For ingredients — this is critical, read every single word:
- raw_text: transcribe the COMPLETE ingredients list verbatim, character by character, including all punctuation, parentheses, asterisks, and footnotes. Do not summarize, truncate, or paraphrase any part of it.
- items: parse EVERY ingredient token regardless of font weight, size, or formatting. Bold, italic, regular, small print — ALL words count equally. A product with 30+ ingredients should have 30+ items. If you think you are done, re-read the label and check for missed items.
- is_sub_ingredient_of: for anything inside parentheses, set this to the immediate parent ingredient name.
- contains_allergens: extract from explicit "Contains:" statement or any bold/capitalized/highlighted ingredient names.
- may_contain_allergens: extract EVERY allergen from "May contain:", "Made in a facility that uses/processes/handles", or any cross-contamination language. Read the full sentence — these warnings list multiple allergens separated by commas and "and"; every single one must be captured. Do not stop at the first allergen in the sentence.

NON-BOLD WORDS ARE NOT OPTIONAL. Treat every word in the ingredients list as equally important regardless of how it is visually styled on the label.

Return strictly valid JSON matching the provided schema. Use null if data is missing.
"""

SCHEMA_DESCRIPTION = """
{
  "product_info": {
    "brand": string | null,
    "product_name": string | null,
    "packaging_type": "fresh|packaged|frozen|canned|bulk|unknown",
    "preparation_state": "raw|cooked|ready_to_eat|unknown",
    "net_weight": { "value": number | null, "unit": string | null }
  },
  "nutrition_facts": {
    "serving_size": { "value": number | null, "unit": string | null },
    "servings_per_container": number | null,
    "per_serving": {
      "calories": number | null,
      "total_fat_g": number | null,
      "saturated_fat_g": number | null,
      "trans_fat_g": number | null,
      "cholesterol_mg": number | null,
      "sodium_mg": number | null,
      "total_carbohydrate_g": number | null,
      "dietary_fiber_g": number | null,
      "total_sugars_g": number | null,
      "added_sugars_g": number | null,
      "protein_g": number | null
    }
  },
  "ingredients": {
    "raw_text": string | null,
    "items": [
      {
        "name": string,
        "is_sub_ingredient_of": string | null
      }
    ] | null,
    "contains_allergens": string[] | null,
    "may_contain_allergens": string[] | null
  }
}
"""


def analyze_food_product(
    product_img: str,
    label_img: str,
    api_key: str | None = None,
) -> dict:
    """
    Send product and label images to Claude and return parsed nutrition data.

    Image preprocessing (OCR crop + encode) for both files is executed in
    parallel via a thread pool, since each operation is independent and
    CPU/IO-bound.

    Args:
        product_img (str): Filesystem path to the product packaging image.
        label_img (str):   Filesystem path to the nutrition label image.
        api_key (str | None): Anthropic API key. Falls back to the
            ``ANTHROPIC_API_KEY`` environment variable when None.

    Returns:
        dict: Parsed nutrition data matching the structure defined in
            SCHEMA_DESCRIPTION.

    Raises:
        anthropic.APIError: If the upstream Anthropic API request fails.
        json.JSONDecodeError: If the model response cannot be parsed as JSON.
        ValueError: If an image file has an unsupported extension.
    """
    client = anthropic.Anthropic(
        api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_product = executor.submit(build_image_block, product_img, False)
        future_label = executor.submit(build_image_block, label_img, False)
        product_block = future_product.result()
        label_block = future_label.result()

    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Product image"},
                    product_block,
                    {"type": "text", "text": "Nutrition label"},
                    label_block,
                    {
                        "type": "text",
                        "text": "Extract nutrition data\n\n" + SCHEMA_DESCRIPTION,
                    },
                ],
            }
        ],
    )

    text = message.content[0].text.strip()
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:-1])

    return json.loads(text)
