Recorded public sources fetched on 2026-10-30. These files are used only by tests.

Matcher regression records fetched on 2026-10-31: `match-kcc.json`,
`match-psgs-deg.json`, `match-pmsfss.json`, and `match-pmsscstb.json` are parsed
official detail/documents/FAQ responses from `https://www.myscheme.gov.in/api/apisetu/`
for the corresponding slugs. Each record retains its original `source_url`.

- `myscheme-pm-kisan.json`: https://www.myscheme.gov.in/api/apisetu/schemes?slug=pm-kisan&lang=en
- `myscheme-search.json`: https://www.myscheme.gov.in/api/apisetu/search/schemes?lang=en&q=%5B%5D&keyword=scholarship&sort=&from=0&size=2
- `myscheme-documents.json`: https://www.myscheme.gov.in/api/apisetu/schemes/62a70e86f038bd8499a6aa53/documents?lang=en
- `myscheme-faqs.json`: https://www.myscheme.gov.in/api/apisetu/schemes/62a70e86f038bd8499a6aa53/faqs?lang=en
- `pib-1.xml`: https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3&reg=3
- `pib-2.xml`: Hindi PIB RSS, fetched through the original redirecting URL (Lang=2, Regid=3, reg=48).
- `pib-panchayati-raj.pdf`: https://static.pib.gov.in/WriteReadData/specificdocs/documents/2026/apr/doc2026424855601.pdf
- `pib-panchayati-raj-page-1.png`: page 1 of that official PDF, rendered with Poppler for image OCR checks.
- `pib-panchayati-raj-scan.pdf`: the same recorded page embedded as an image-only PDF for scanned-page OCR checks.
