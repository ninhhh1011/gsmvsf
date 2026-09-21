# Pre-migration dependency inventory

Audit baseline: `a2f43a3`, original dirty tree retained. Audit performed before any deletion.
All line references below describe the superseded baseline, not the final runtime. Dataset references are frozen source provenance and must remain untouched. Current README/AGENTS/architecture/config instructions will be updated. Historical Week 1/2 reports and Week 3 original plan remain evidence.

| File | Classification | Matching lines |
|---|---|---|
| `.gitignore` | A active runtime | 36, 37, 38, 39, 40 |
| `AGENTS.md` | E historical documentation | 37, 50 |
| `.env.example` | B configuration | 11, 13, 14 |
| `claude_week1_skills/README.md` | E historical documentation | 6 |
| `scripts/smoke_test_week3.py` | C infrastructure/scripts | 5, 40, 43, 58, 59, 60, 61, 62, 64, 68 |
| `scripts/smoke_test.py` | C infrastructure/scripts | 3, 5, 25, 42, 43, 46, 52, 53, 57, 65, 66, 68, 74, 85, 88, 89, 92, 93, 95, 96, 126, 130, 146, 151, 165, 168 |
| `scripts/benchmark_week3.py` | C infrastructure/scripts | 62 |
| `scripts/benchmark_realtime_map_matching.py` | C infrastructure/scripts | 36, 221, 225, 230, 367 |
| `.claude/skills/week1-map-matching/SKILL.md` | E historical documentation | 3, 45, 46, 97, 98, 125, 127, 138, 156, 205, 216, 220, 224, 242, 252, 264, 265, 266 |
| `.claude/skills/osrm-workflow/SKILL.md` | E historical documentation | 2, 3, 6, 10, 19, 25, 39, 41, 43, 45, 47, 50, 71, 79, 95, 97, 99, 115, 126, 156, 166, 170, 206, 214, 218, 228, 231, 256, 270, 282, 284, 295 |
| `claude_week1_skills/.claude/skills/week1-map-matching/SKILL.md` | E historical documentation | 3, 45, 46, 97, 98, 125, 127, 138, 156, 205, 216, 220, 224, 242, 252, 264, 265, 266 |
| `backend/tests/conftest.py` | D tests | 30, 31, 32 |
| `claude_week1_skills/.claude/skills/osrm-workflow/SKILL.md` | E historical documentation | 2, 3, 6, 10, 19, 25, 39, 41, 43, 45, 47, 50, 71, 79, 95, 97, 99, 115, 126, 156, 166, 170, 206, 214, 218, 228, 231, 256, 270, 282, 284, 295 |
| `backend/tests/test_candidate_api.py` | D tests | 21 |
| `backend/tests/test_candidate_search_service.py` | D tests | 26 |
| `backend/tests/test_candidate_scenarios.py` | D tests | 42, 302 |
| `backend/app/api/v1/realtime.py` | A active runtime | 30, 103, 109, 354 |
| `backend/app/api/v1/map_match.py` | A active runtime | 11, 13, 23, 30, 31, 39, 40, 41, 70, 76, 109, 110 |
| `backend/app/api/v1/health.py` | A active runtime | 19, 22, 25, 26, 30, 33, 38 |
| `backend/app/api/v1/candidate.py` | A active runtime | 23, 36, 37, 42, 43 |
| `backend/tests/test_routing_models.py` | D tests | 61, 66 |
| `backend/tests/test_osrm_routing_adapter.py` | D tests | 2, 14, 18, 48, 55, 59, 76, 85, 93, 102, 114 |
| `backend/tests/test_map_matching.py` | D tests | 116, 117, 119, 120, 121, 123, 128, 129, 130, 140, 147, 148, 149, 161, 170, 225, 226, 228, 230, 232, 244 |
| `Makefile` | C infrastructure/scripts | 7, 12, 27, 28, 29, 30, 31, 32, 33, 34, 52, 55, 61 |
| `backend/app/config.py` | B configuration | 26, 28, 29, 30, 32, 33 |
| `backend/app/services/routing/osrm_routing_adapter.py` | A active runtime | 2, 4, 5, 27, 29, 38, 49, 50, 57, 88, 89, 131, 140, 141, 148, 149, 157, 158, 165, 166, 170, 175, 176, 179, 184, 185, 192 |
| `backend/app/services/routing/models.py` | A active runtime | 4, 29 |
| `backend/app/services/routing/mock_adapter.py` | A active runtime | 4 |
| `backend/app/services/routing/graphhopper_routing_adapter.py` | A active runtime | 31, 74 |
| `backend/app/services/routing/engine.py` | A active runtime | 4 |
| `docs/WEEK_3_IMPLEMENTATION_PLAN.md` | E historical documentation | 6, 18, 34, 36, 60, 61, 99, 112, 114, 179, 184, 194, 195, 198, 200, 201, 202, 203, 205, 208, 209, 213, 216, 222, 454, 456, 458, 460, 461, 465, 468, 473, 474, 475, 492, 531, 547, 548 |
| `docs/WEEK_3.md` | E historical documentation | 5, 62 |
| `docs/WEEK_2_IMPLEMENTATION_PLAN.md` | E historical documentation | 346 |
| `docs/WEEK_2.md` | E historical documentation | 290 |
| `docs/WEEK_1_TECHNICAL_AUDIT.md` | E historical documentation | 15, 186, 252, 257, 260, 266, 267, 344, 393, 394, 398, 449, 486 |
| `docs/WEEK_1_REMAINING_PLAN.md` | E historical documentation | 92, 153 |
| `docs/WEEK_1_REALTIME_POLICY.md` | E historical documentation | 71 |
| `docs/WEEK_1_FREEZE.md` | E historical documentation | 99, 100, 105, 122 |
| `docs/WEEK_1_ACCEPTANCE_REPORT.md` | E historical documentation | 52, 60, 76, 99, 102, 104, 111, 290, 294, 316, 420, 489, 511, 513, 537, 539, 541, 655, 721, 722 |
| `docs/WEEK_1.md` | E historical documentation | 142, 146, 218, 231 |
| `docs/ROUTING_STRATEGY.md` | E historical documentation | 5, 57, 140, 194, 242, 253, 256, 259, 265, 298, 300, 302, 319, 422, 442, 448, 453, 454, 464, 466 |
| `docs/GRAPHHOPPER_OSRM_INVENTORY.md` | E historical documentation | 1, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222, 223, 224, 225, 226, 227, 228, 229, 230, 231, 232, 233, 234, 235, 236, 237, 238, 239, 240, 241, 242, 243, 244, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269, 270, 271, 272, 273, 274, 275, 276, 277, 278, 279, 280, 281, 282, 283, 284, 285, 286, 287, 288, 289, 290, 291, 292, 293, 294, 295, 296, 297, 298, 299, 300, 301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 311, 312, 313, 314, 315, 316, 317, 318, 319, 320, 321, 322, 323, 324, 325, 326, 327, 328, 329, 330, 331, 332, 333, 334, 335, 336, 337, 338, 339, 340, 341, 342, 343, 344, 345, 346, 347, 348, 349, 350, 351, 352, 353, 354, 355, 356, 357, 358, 359, 360, 361, 362, 363, 364, 365, 366, 367, 368, 369, 370, 371, 372, 373, 374, 375, 376, 377, 378, 379, 380, 381, 382, 383, 384, 385, 386, 387, 388, 389, 390, 391, 392, 393, 394, 395, 396, 397, 398, 399, 400, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410, 411, 412, 413, 414, 415, 416, 417, 418, 419, 420, 421, 422, 423, 424, 425, 426, 427, 428, 429, 430, 431, 432, 433, 434, 435, 436, 437, 438, 439, 440, 441, 442, 443, 444, 445, 446, 447, 448, 449, 450, 451, 452, 453, 454, 455, 456, 457, 458, 459, 460, 461, 462, 463, 464, 465, 466, 467, 468, 469, 470, 471, 472, 473, 474, 475, 476, 477, 478, 479, 480, 481, 482, 483, 484, 485, 486, 487, 488, 489, 490, 491, 492, 493, 494, 495, 496, 497, 498, 499, 500, 501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 511, 512, 513, 514, 515, 516, 517, 518, 519, 520, 521, 522, 523, 524, 525, 526, 527, 528, 529, 530, 531, 532, 533, 534, 535, 536, 537, 538, 539, 540, 541, 542, 543, 544, 545, 546, 547, 548, 549, 550, 551, 552, 553, 554, 555, 556, 557, 558, 559, 560, 561, 562, 563, 564, 565, 566, 567, 568, 569, 570, 571, 572, 573, 574, 575, 576, 577, 578, 579, 580, 581, 582, 583, 584, 585, 586, 587, 588, 589, 590, 591 |
| `docs/GRAPHHOPPER_MIGRATION_AUDIT.md` | E historical documentation | 17, 19, 20, 23, 24, 28, 30 |
| `docs/EXTERNAL_GPS_DATA.md` | E historical documentation | 242 |
| `docs/DECISIONS.md` | E historical documentation | 15, 17, 19, 21, 31, 33, 65, 79, 91, 101, 103 |
| `docs/DATA_CONTRACT.md` | E historical documentation | 3, 17, 99 |
| `docs/ARCHITECTURE.md` | E historical documentation | 14, 22, 25, 28, 58, 64, 99, 121, 123, 133 |
| `docker-compose.yml` | C infrastructure/scripts | 19, 20, 21, 25, 27, 29, 67, 68, 69, 74, 81, 86 |
| `backend/app/services/candidate/service.py` | A active runtime | 48, 60, 63, 65 |
| `runtime/osrm/profiles/car.lua` | F generated/runtime artifacts | 1 |
| `dataset_v1/DATA_DICTIONARY.md` | E historical documentation | 3 |
| `backend/app/services/map_matching/__init__.py` | A active runtime | 17, 18, 19, 20, 21, 22, 23, 51, 52, 53, 54, 55, 56, 57 |
| `backend/app/services/map_matching/service.py` | A active runtime | 14, 15, 45, 51, 58, 61, 71, 73, 83, 85, 88, 117, 120, 121 |
| `backend/app/services/map_matching/segment_resolver.py` | A active runtime | 37, 39, 120 |
| `backend/app/services/map_matching/osrm_adapter.py` | A active runtime | 1, 9, 10, 14, 15, 19, 20, 24, 25, 29, 30, 35, 60, 61, 98, 117, 123, 159, 160, 184, 185, 186, 187, 190, 208, 210, 212, 215, 217, 219, 221, 227, 230, 233, 234, 239, 241 |
| `backend/app/services/map_matching/models.py` | A active runtime | 48 |
| `backend/app/services/map_matching/graphhopper_adapter.py` | A active runtime | 7, 9, 28, 196 |
| `backend/app/services/map_matching/engine.py` | A active runtime | 4, 10 |
| `dataset_v1/REQUIREMENT_DATA_MATRIX.md` | E historical documentation | 32, 35 |
| `dataset_v1/validation/update_docs.py` | F generated/runtime artifacts | 13, 105 |
| `dataset_v1/README.md` | E historical documentation | 68 |
| `README.md` | E historical documentation | 5, 32, 34, 85, 101, 102, 114, 117, 123, 160, 163, 166, 175, 178, 179, 185, 189, 193, 214, 236, 239, 306, 307, 313, 317, 319 |
| `PLAN.md` | E historical documentation | 5, 10, 16, 18, 20, 21, 22, 23, 24, 25, 26, 34, 44, 45, 57, 59, 83, 85, 94, 114, 118, 120, 122, 123, 129, 133, 162, 203, 209, 222 |
| `dataset_v1/generators/04_patch_semantic_dataset.py` | F generated/runtime artifacts | 361 |
| `.claude/skills/open-map-stack/README.md` | E historical documentation | 138 |
| `.claude/skills/open-map-stack/SKILL.md` | E historical documentation | 107 |
| `.claude/skills/open-map-stack/references/data-sources.md` | E historical documentation | 383 |
| `.claude/skills/open-map-stack/references/analytics.md` | E historical documentation | 332, 336, 466 |
| `.claude/skills/open-map-stack/references/services-and-scale.md` | E historical documentation | 22, 35, 153, 166 |
