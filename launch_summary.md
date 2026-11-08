# Launch summary: Next month rebuild
Start 2026-12-01, 31 days. Meta daily = monthly / 31; Google daily = monthly / 30.4 (Google's monthly billing cap). Everything is imported PAUSED.

| Channel | Campaign | Monthly | Daily | Expected CPA | Projected trials |
|---|---|---:|---:|---:|---:|
| Meta | META_US_PROSP_AdvPlus_Scale | $44,000 | $1,419 | $255 | 173 |
| Meta | META_US_PROSP_CreativeTest | $15,000 | $484 | $290 | 52 |
| Meta | META_US_RT_14d | $6,000 | $194 | $300 | 20 |
| Google | GOOG_US_Search_Brand | $9,000 | $296 | $155 | 58 |
| Google | GOOG_US_Search_NonBrand | $30,000 | $987 | $285 | 105 |
| Google | GOOG_US_PMax | $16,000 | $526 | $320 | 50 |
| Google | GOOG_UK_Search_NonBrand (paused) | $0 | $0 | - | 0 |

**Total:** $120,000 (Meta $65,000, Google $55,000)
**Projected:** 458 trials at a blended $262 CPA (target $250-$280).

## Validation
- No blocking errors.
- Warning: Meta ad 'UGC_Founder_v3_HookA' is new creative. Upload ugc_founder_v3a.mp4 before launch.
- Warning: Meta ad 'UGC_Founder_v3_HookB' is new creative. Upload ugc_founder_v3b.mp4 before launch.
- Warning: Meta ad 'Static_Agency_ROI' is new creative. Upload static_agency_roi.png before launch.
- Warning: Meta ad 'Demo_15s_Cutdown' is new creative. Upload demo_15s.mp4 before launch.
- Warning: Meta ad 'RT_Demo_Objections' is new creative. Upload demo_objections.mp4 before launch.
- Warning: Meta ad 'RT_Testimonial_v2' is new creative. Upload testimonial_v2.mp4 before launch.

## Before you switch anything on
- [ ] Test trial signup on the live signup flow: StartTrial fires in Meta Events Manager (browser + server, deduplicated) and Trial Start fires in Google Ads.
- [ ] A test click with UTMs shows up in PostHog under the right utm_source / utm_content.
- [ ] Audiences Trial_Starters_180d and Customers_All exist and are populated.
- [ ] New creative files uploaded (see warnings).
- [ ] Enable campaigns, then check spend after 2 hours and again next morning.
