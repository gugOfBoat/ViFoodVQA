# Tổng Kết Full Evaluation GPT-5.2 và GPT-5.5

Báo cáo này được tổng hợp từ 3 thư mục output:

- `outputs/gpt52_full_20260430`
- `outputs/gpt55_kg_20260430_074852`
- `outputs/gpt55_no_kg_20260430_074852`

Ngày chốt số liệu: 2026-05-01.

Quy ước bôi đậm:

- Với các metric càng cao càng tốt, giá trị cao nhất trong bảng được **in đậm**.
- Riêng `Parse failure` và `Avg answer latency` là metric càng thấp càng tốt, nên giá trị tốt nhất theo hướng thấp nhất được **in đậm**.

## Độ Đầy Đủ Của Kết Quả

Tất cả prediction files dự kiến đều đã chạy đủ. Mỗi file model-condition có 1,410 dòng tương ứng với 1,410 mẫu test.

| Model | Nhóm output | Conditions | Rows |
| --- | --- | --- | ---: |
| `gpt_5_2` | `gpt52_full_20260430` | 8/8 | 11,280 |
| `gpt_5_5` | `gpt55_kg_20260430_074852` + `gpt55_no_kg_20260430_074852` | 8/8 | 11,280 |
| tất cả | combined | **16/16** | **22,560** |

Độ đầy đủ của classifier cache:

| Model | Số dòng classifier | Ghi chú |
| --- | ---: | --- |
| `gpt_5_2` | 1,410 | Dùng cho các điều kiện KG retrieval. |
| `gpt_5_5` | 1,410 | Dùng cho các điều kiện KG retrieval. |

## Accuracy Tổng Thể

| Model | Condition | Đúng / Tổng | Accuracy | Parse failure | QType classifier | Avg answer latency |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `gpt_5_2` | `no_kg_0shot` | 1,243 / 1,410 | 88.16% | 0.50% | - | 5.37s |
| `gpt_5_2` | `no_kg_1shot` | 1,249 / 1,410 | 88.58% | 0.35% | - | 6.15s |
| `gpt_5_2` | `no_kg_2shot` | 1,216 / 1,410 | 86.24% | 1.35% | - | 15.13s |
| `gpt_5_2` | `hybrid` | 1,250 / 1,410 | 88.65% | 1.06% | 96.38% | 5.14s |
| `gpt_5_2` | `graph_only` | 1,244 / 1,410 | 88.23% | 1.21% | 96.38% | 5.86s |
| `gpt_5_2` | `vector_only` | 1,228 / 1,410 | 87.09% | 1.42% | 96.38% | 12.88s |
| `gpt_5_2` | `bm25` | 1,228 / 1,410 | 87.09% | 1.42% | 96.38% | 7.38s |
| `gpt_5_2` | `oracle` | 1,342 / 1,410 | 95.18% | 0.64% | - | 4.90s |
| `gpt_5_5` | `no_kg_0shot` | 1,277 / 1,410 | 90.57% | **0.00%** | - | 7.57s |
| `gpt_5_5` | `no_kg_1shot` | 1,280 / 1,410 | 90.78% | **0.00%** | - | 8.35s |
| `gpt_5_5` | `no_kg_2shot` | 1,281 / 1,410 | 90.85% | **0.00%** | - | 13.50s |
| `gpt_5_5` | `hybrid` | 1,279 / 1,410 | 90.71% | **0.00%** | **97.52%** | 7.23s |
| `gpt_5_5` | `graph_only` | 1,278 / 1,410 | 90.64% | **0.00%** | **97.52%** | 7.38s |
| `gpt_5_5` | `vector_only` | 1,265 / 1,410 | 89.72% | **0.00%** | **97.52%** | 7.25s |
| `gpt_5_5` | `bm25` | 1,266 / 1,410 | 89.79% | 0.71% | **97.52%** | 6.08s |
| `gpt_5_5` | `oracle` | **1,346 / 1,410** | **95.46%** | 0.92% | - | **4.54s** |

`Avg answer latency` lấy từ trường `latency_s` trong prediction rows, nên chỉ đo thời gian sinh câu trả lời. Con số này chưa bao gồm thời gian retrieval KG hoặc thời gian classifier.

## Nhận Xét Chính

- `gpt_5_5` mạnh hơn `gpt_5_2` nhất quán trên toàn bộ các condition có thể so sánh. Mức tăng thường nằm trong khoảng +2.06 đến +2.70 điểm phần trăm ở các condition non-oracle, và tăng mạnh nhất ở `no_kg_2shot` với +4.61 điểm.
- `oracle` vẫn là upper bound rõ ràng cho cả hai model: `gpt_5_2` đạt 95.18%, còn `gpt_5_5` đạt 95.46%. Khoảng cách từ condition non-oracle tốt nhất đến oracle là 6.52 điểm với `gpt_5_2` và 4.61 điểm với `gpt_5_5`.
- Condition non-oracle tốt nhất khác nhau theo model:
  - `gpt_5_2`: `hybrid` tốt nhất với 88.65%, chỉ hơn `no_kg_1shot` khoảng +0.07 điểm.
  - `gpt_5_5`: `no_kg_2shot` tốt nhất với 90.85%, chỉ hơn `hybrid` khoảng +0.14 điểm.
- KG retrieval có ích nhất khi dựa trên graph. `hybrid` và `graph_only` gần như ngang nhau, trong khi `vector_only` và `bm25` yếu hơn rõ ở retrieval metrics.
- `gpt_5_5` ổn định hơn về parsing: không có parse failure ở `no_kg_*`, `hybrid`, `graph_only`, và `vector_only`. `gpt_5_2` vẫn có parse failure nhỏ nhưng lặp lại, đặc biệt ở `vector_only`, `bm25`, và `no_kg_2shot`.
- Few-shot không tự động tốt hơn. Với `gpt_5_2`, `no_kg_2shot` giảm xuống 86.24% và latency tăng mạnh. Với `gpt_5_5`, `no_kg_2shot` là non-oracle tốt nhất, nhưng mức cải thiện so với `no_kg_1shot` chỉ là +0.07 điểm.

## So Sánh Model Theo Condition

| Condition | GPT-5.2 | GPT-5.5 | Delta của GPT-5.5 |
| --- | ---: | ---: | ---: |
| `no_kg_0shot` | 88.16% | **90.57%** | +2.41 pp |
| `no_kg_1shot` | 88.58% | **90.78%** | +2.20 pp |
| `no_kg_2shot` | 86.24% | **90.85%** | **+4.61 pp** |
| `hybrid` | 88.65% | **90.71%** | +2.06 pp |
| `graph_only` | 88.23% | **90.64%** | +2.41 pp |
| `vector_only` | 87.09% | **89.72%** | +2.62 pp |
| `bm25` | 87.09% | **89.79%** | +2.70 pp |
| `oracle` | 95.18% | **95.46%** | +0.28 pp |

## Retrieval Metrics

| Model | Condition | Precision@10 | Recall@10 | F1@10 |
| --- | --- | ---: | ---: | ---: |
| `gpt_5_2` | `hybrid` | 0.3311 | 0.4067 | 0.3548 |
| `gpt_5_2` | `graph_only` | 0.3310 | 0.4064 | 0.3547 |
| `gpt_5_2` | `vector_only` | 0.0289 | 0.2357 | 0.0509 |
| `gpt_5_2` | `bm25` | 0.0147 | 0.1331 | 0.0262 |
| `gpt_5_2` | `oracle` | **1.0000** | **1.0000** | **1.0000** |
| `gpt_5_5` | `hybrid` | 0.3608 | 0.4904 | 0.3984 |
| `gpt_5_5` | `graph_only` | 0.3602 | 0.4872 | 0.3973 |
| `gpt_5_5` | `vector_only` | 0.0297 | 0.2453 | 0.0525 |
| `gpt_5_5` | `bm25` | 0.0160 | 0.1483 | 0.0288 |
| `gpt_5_5` | `oracle` | **1.0000** | **1.0000** | **1.0000** |

Nếu bỏ qua `oracle`, condition retrieval tốt nhất là `gpt_5_5 hybrid` với Precision@10 = **0.3608**, Recall@10 = **0.4904**, và F1@10 = **0.3984**.

Diễn giải retrieval:

- `hybrid` chỉ nhỉnh hơn `graph_only` một chút, cho thấy pipeline hybrid hiện tại vẫn phụ thuộc mạnh vào chất lượng graph traversal.
- `vector_only` và `bm25` có Precision@10 rất thấp. Model vẫn trả lời đúng nhiều câu nhờ ảnh, câu hỏi, và prior knowledge, nhưng hai strategy này yếu nếu xét vai trò evidence retriever.
- Khoảng cách lớn giữa non-oracle và oracle cho thấy KG evidence thật sự có giá trị khi triple đúng được đưa vào prompt. Nút thắt chính hiện tại là retrieval quality, không phải khả năng model sử dụng triple tốt.

## Highlight Theo QType

Condition non-oracle tốt nhất theo từng question type:

| Model | QType | Total | Best non-oracle | Best acc. | Worst non-oracle | Worst acc. |
| --- | --- | ---: | --- | ---: | --- | ---: |
| `gpt_5_2` | allergen_restrictions | 78 | `no_kg_1shot` | **93.59%** | `graph_only` | 88.46% |
| `gpt_5_2` | cooking_technique | 198 | `no_kg_1shot` | **97.98%** | `bm25` | 92.93% |
| `gpt_5_2` | dietary_restrictions | 151 | `bm25` | **84.11%** | `no_kg_2shot` | 80.13% |
| `gpt_5_2` | dish_classification | 170 | `hybrid` | **95.29%** | `vector_only` | 92.94% |
| `gpt_5_2` | flavor_profile | 145 | `graph_only` | **88.28%** | `no_kg_2shot` | 79.31% |
| `gpt_5_2` | food_pairings | 115 | `hybrid` | **92.17%** | `no_kg_0shot` | 86.96% |
| `gpt_5_2` | ingredient_category | 263 | `bm25` | **84.41%** | `no_kg_2shot` | 80.23% |
| `gpt_5_2` | ingredients | 206 | `graph_only` | **92.23%** | `bm25` | 89.32% |
| `gpt_5_2` | origin_locality | 82 | `no_kg_0shot` | **79.27%** | `bm25` | 67.07% |
| `gpt_5_2` | substitution_rules | 2 | `bm25` | **100.00%** | `no_kg_0shot` | 50.00% |
| `gpt_5_5` | allergen_restrictions | 78 | `graph_only` | **93.59%** | `bm25` | 89.74% |
| `gpt_5_5` | cooking_technique | 198 | `bm25` | **98.48%** | `graph_only` | 96.46% |
| `gpt_5_5` | dietary_restrictions | 151 | `no_kg_1shot` | **88.08%** | `bm25` | 84.77% |
| `gpt_5_5` | dish_classification | 170 | `graph_only` | **96.47%** | `bm25` | 94.12% |
| `gpt_5_5` | flavor_profile | 145 | `no_kg_2shot` | **91.72%** | `vector_only` | 86.90% |
| `gpt_5_5` | food_pairings | 115 | `no_kg_0shot` | **93.91%** | `vector_only` | 90.43% |
| `gpt_5_5` | ingredient_category | 263 | `no_kg_0shot` | **84.79%** | `no_kg_2shot` | 81.75% |
| `gpt_5_5` | ingredients | 206 | `no_kg_2shot` | **94.66%** | `bm25` | 92.23% |
| `gpt_5_5` | origin_locality | 82 | `no_kg_2shot` | **87.80%** | `vector_only` | 80.49% |
| `gpt_5_5` | substitution_rules | 2 | `bm25` | **100.00%** | `vector_only` | 50.00% |

Ghi chú:

- `substitution_rules` chỉ có 2 mẫu test, nên phần trăm của qtype này không ổn định và không nên diễn giải quá mạnh.
- `origin_locality`, `dietary_restrictions`, và `ingredient_category` vẫn là các nhóm khó hơn so với `cooking_technique`, `dish_classification`, và `ingredients`.
- Condition tốt nhất thay đổi theo qtype. Vì vậy, một hướng cải thiện hợp lý là chọn retrieval/prompt mode theo predicted qtype thay vì dùng một strategy cố định cho tất cả câu hỏi.

## Kết Luận và Báo Cáo

1. Nên dùng `oracle` như upper-bound evidence result, không xem đây là setting triển khai thực tế.
2. Nên dùng `hybrid` làm KG retrieval condition chính trong báo cáo vì đây là non-oracle tốt nhất của `gpt_5_2` và vẫn cạnh tranh với `gpt_5_5`.
3. Cần ghi rõ `gpt_5_5 no_kg_2shot` nhỉnh hơn `gpt_5_5 hybrid`, nhưng chênh lệch chỉ là 2 câu đúng trên 1,410 mẫu.
4. Nên xem `vector_only` và `bm25` là ablation cho thấy điểm yếu retrieval, không phải ứng viên retrieval mạnh cho production.
5. Nên báo cáo qtype classifier accuracy vì chỉ số này cao nhưng chưa hoàn hảo: 96.38% với `gpt_5_2`, 97.52% với `gpt_5_5`.
6. Khi bàn về tốc độ, cần nói rõ `no_kg_2shot` chậm hơn đáng kể do prompt dài hơn; `latency_s` không bao gồm thời gian KG retrieval hoặc classifier.

