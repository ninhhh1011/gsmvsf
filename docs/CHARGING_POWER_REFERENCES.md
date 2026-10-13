# Charging power references — 2026-10-13

Customer requested a few broad web-sourced charging figures rather than a complete per-vehicle technical survey. These are charging powers, not motor powers. Canonical Dataset V1 is unchanged.

| Item | Published figure | Primary source | Runtime use |
|---|---|---|---|
| VinFast car charging posts | 30, 60, 150 kW (also 250 kW in the guide) | [VinFast charging guide](https://vinfastauto.com/vn_vi/huong-dan-sac-pin-o-to-dien-vinfast) | Representative station assumption: 60 kW; individual Dataset stations do not specify their power. |
| VF 3 | Maximum DC charging power 24 kW; fastest 10–70% session about 36 minutes | [VinFast VF 3 FAQ](https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap/cau-hoi-xe-o-to/san-pham/vf-3) | Model-specific maximum acceptance: 24 kW. |
| Evo200 chargers | 400 W and 1,000 W | [VinFast Evo200 specifications](https://vinfastauto.com/vn_vi/thong-so-ky-thuat-evo200) | Representative motorcycle assumption: 0.4 kW, configurable to 1 kW for the faster charger. |

Other cars' 30 kW acceptance is a broad configurable simulation assumption, not a verified specification of every model. Similarly, the motorcycle class fallback does not establish compatibility or charging limits for every bike. Vehicle capability and connector eligibility remain independently enforced.

Battery-side modeled power uses the lower station/vehicle limit and configured efficiency. Efficiency, connection setup and a simplified high-SOC taper remain project assumptions. Peak published power is not a guaranteed session average; exact time depends on battery temperature, charger sharing and the vehicle charging curve. The model predicts a service plan, never proof that actual charging occurred.
