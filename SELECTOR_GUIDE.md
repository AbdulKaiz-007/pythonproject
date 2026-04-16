# How to Find CSS Selectors for "Book Now" (and other steps)

1. Open your ticketing page in Chrome.
2. Right click the target element (for example: **Book Now**) and choose **Inspect**.
3. In DevTools Elements panel, right click highlighted node -> **Copy** -> **Copy selector**.
4. Prefer stable attributes over long nested selectors:
   - Good: `button[data-testid='book-now']`
   - Better: `button[aria-label='Book tickets']`
   - Avoid: `#app > div:nth-child(4) > div > button`
5. Validate selector in Console:
   - `document.querySelector("button[data-testid='book-now']")`
   - If it returns `null`, selector is wrong or element is inside an iframe/shadow DOM.
6. Test clickability in Selenium by running script with small timeout first.

## Mapping for `selectors.json`

- `book_button`: Main CTA that appears when booking opens.
- `english_filter`: Language filter button/chip.
- `imax_filter`: Format filter button/chip.
- `seat_map_ready`: Control that opens a specific showtime or seat layout.
- `continue_to_payment`: Continue/Proceed CTA after seat selection.
- `payment_page_anchor`: Any element that appears only on payment page.

## Notes

- If the site changes HTML often, inspect and update selectors before release day.
- If target control is inside an iframe, Selenium must switch to that iframe first.
