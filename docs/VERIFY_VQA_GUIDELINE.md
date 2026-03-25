# Guideline Verify VQA cho dự án ViFoodVQA

## 1. Mục đích

Tài liệu này hướng dẫn cách verify các dòng VQA trong dự án **ViFoodVQA** để các thành viên trong nhóm thống nhất cách đánh giá và xử lý dữ liệu.

Ở giai đoạn hiện tại, nhóm chọn **kịch bản 2** cho benchmark:

- verify **question**
- verify **choices**
- verify **triples_used**
- **không lấy reason làm trọng tâm verify**

Mục tiêu cuối cùng là làm rõ vai trò của **ViFoodKG** trong bài toán VQA, cụ thể là so sánh giữa:

- model trả lời **không có KG**
- model trả lời **có retrieve triples từ KG**

Vì vậy, độ đúng đắn của `triples_used` là một thành phần rất quan trọng.

---

## 2. Phạm vi verify

Khi verify một dòng VQA, thành viên cần tập trung vào 3 thành phần chính:

### 2.1. Question

Kiểm tra xem câu hỏi có:

- đúng với nội dung ảnh
- đúng với `qtype`
- rõ ràng, không mơ hồ
- không hỏi sai fact
- không dựa vào thông tin ngoài ảnh và ngoài KG một cách vô căn cứ

### 2.2. Choices

Kiểm tra xem 4 lựa chọn có:

- cùng loại với đáp án đúng
- không bị lạc loại
- không có nhiều đáp án đúng
- không quá dễ hoặc quá vô lý
- phù hợp với câu hỏi

### 2.3. Triples Used

Kiểm tra xem các triple được dùng để sinh câu hỏi có:

- liên quan tới ảnh hiện tại
- đúng fact
- hỗ trợ được cho câu hỏi
- cần giữ nguyên, loại bỏ, hay chỉnh sửa

---

## 3. Thành phần không phải trọng tâm verify

### 3.1. Reason

Hiện tại nhóm **không dùng reason làm thành phần chính để benchmark**, nên:

- không bắt buộc sửa reason
- không dùng reason làm tiêu chí KEEP/DROP chính
- chỉ xem reason như thông tin tham khảo nếu cần hiểu model đã suy luận thế nào

### 3.2. Triples Retrieved

`triples_retrieved` là tập triple được retrieve từ tất cả `food_items` trong ảnh.

Ở bước verify VQA hiện tại:

- `triples_retrieved` chỉ dùng để tham khảo thêm ngữ cảnh
- **không phải** đối tượng verify chính
- đối tượng verify chính là `triples_used`

---

## 4. Nguyên tắc chung khi verify

### 4.1. Ưu tiên tính đúng đắn hơn tính đẹp

Nếu câu hỏi viết chưa hay nhưng fact đúng, có thể sửa nhẹ để giữ lại.
Nếu câu hỏi nghe có vẻ ổn nhưng fact sai, phải ưu tiên sửa hoặc drop.

### 4.2. Không suy diễn quá mức

Chỉ giữ VQA nếu có đủ căn cứ từ:

- ảnh
- `food_items`
- `image_desc`
- `triples_used`

Không tự thêm tri thức bên ngoài nếu không có cơ sở rõ ràng.

### 4.3. Verify theo ngữ cảnh của ảnh hiện tại

Một triple có thể đúng trong KG nói chung, nhưng **không phù hợp với ảnh hiện tại**.
Khi đó, trong ngữ cảnh của VQA này, triple đó vẫn có thể bị đánh giá là không phù hợp.

### 4.4. Không overwrite triple gốc một cách tùy tiện

Nếu thấy triple sai nhưng vẫn còn cứu được, verifier có thể chọn **Needs edit**.
Khi đó, hệ thống nên:

- tạo triple revised mới
- remap VQA hiện tại sang triple mới
- không âm thầm sửa đè triple gốc

---

## 5. Quy trình verify cho một VQA

Mỗi thành viên nên đi theo đúng thứ tự sau:

### Bước 1. Quan sát ảnh

Xem:

- ảnh
- `food_items`
- `image_desc`

Mục tiêu là hiểu ngữ cảnh món ăn trong ảnh trước khi đọc câu hỏi.

### Bước 2. Đọc VQA

Xem:

- `qtype`
- `question`
- 4 choices
- `answer`

Tự trả lời câu hỏi:

- câu này có hợp lý với ảnh không?
- đáp án đúng có thực sự đúng không?

### Bước 3. Kiểm tra từng triple trong `triples_used`

Với mỗi triple, xác định 1 trong 4 trạng thái:

- **Valid**
- **Invalid**
- **Needs edit**
- **Unsure**

### Bước 4. Chấm phiếu verify VQA

Chấm theo 3 tiêu chí:

- **Q0**: Triple Used Validity
- **Q1**: Question Validity
- **Q2**: Choice Quality

### Bước 5. Ra quyết định cuối

Chốt:

- **KEEP**
- **DROP**

---

## 6. Hướng dẫn verify `triples_used`

### 6.1. Khi nào chọn Valid

Chọn **Valid** nếu triple:

- đúng fact
- liên quan tới ảnh hoặc món trong ảnh
- có thể dùng để hỗ trợ câu hỏi hiện tại
- không cần chỉnh sửa nội dung

Ví dụ:

- `Phở bò — hasIngredient — Thịt bò`
- `Bún bò Huế — originRegion — Huế`

### 6.2. Khi nào chọn Invalid

Chọn **Invalid** nếu triple:

- sai fact
- không liên quan tới ảnh
- là hallucination
- dùng cho câu hỏi hiện tại là không phù hợp

Ví dụ:

- ảnh là bún bò nhưng triple lại nói về pizza
- triple nói món có thành phần A nhưng thực tế không đúng

### 6.3. Khi nào chọn Needs edit

Chọn **Needs edit** nếu triple:

- có liên quan
- đúng hướng nhưng sai chi tiết
- sửa lại thì vẫn dùng được

Ví dụ:

- relation đúng nhưng target sai
- subject đúng nhưng evidence sai
- triple đúng ý lớn nhưng cần chỉnh chi tiết fact

Ví dụ cụ thể:

- gốc: `Bún bò Huế — originRegion — Miền Nam`
- sửa thành: `Bún bò Huế — originRegion — Huế`

### 6.4. Khi nào chọn Unsure

Chọn **Unsure** nếu:

- chưa đủ căn cứ kết luận đúng/sai
- ảnh quá mơ hồ
- triple có vẻ hợp lý nhưng chưa chắc

Không nên lạm dụng trạng thái này. Chỉ dùng khi thật sự chưa đủ căn cứ.

---

## 7. Hướng dẫn chấm 3 tiêu chí verify

### 7.1. Q0 — Triple Used Validity

**Điểm 1**

- triple sai rõ ràng
- triple không hỗ trợ được câu hỏi
- dùng triple này sẽ làm benchmark nhiễu

**Điểm 2**

- triple có vấn đề
- đúng một phần nhưng không đủ tin cậy
- cần chỉnh hoặc còn mơ hồ

**Điểm 3**

- triple đúng
- hỗ trợ được câu hỏi
- có thể giữ

**Điểm 4**

- triple đúng, rõ và rất phù hợp
- triple đóng vai trò tốt trong việc tạo câu hỏi

### 7.2. Q1 — Question Validity

**Điểm 1**

- câu hỏi sai bản chất
- hỏi sai đối tượng
- không khớp ảnh

**Điểm 2**

- câu hỏi còn mơ hồ
- diễn đạt lỗi
- có thể gây hiểu nhầm

**Điểm 3**

- câu hỏi đúng
- dễ hiểu
- phù hợp ảnh

**Điểm 4**

- câu hỏi rất rõ
- tự nhiên
- đúng trọng tâm

### 7.3. Q2 — Choice Quality

**Điểm 1**

- đáp án đúng bị sai
- hoặc có nhiều đáp án đúng

**Điểm 2**

- distractor lệch loại
- choices không đồng nhất
- logic đáp án yếu

**Điểm 3**

- đáp án đúng
- choices nhìn chung ổn

**Điểm 4**

- đáp án đúng
- distractor cùng loại, hợp lý và đủ khó

---

## 8. Luật KEEP / DROP

Nhóm nên dùng luật sau để thống nhất:

### DROP nếu:

- `Q0 <= 2`
- hoặc `Q1 <= 2`

### Với `Q2 <= 2`:

- xem là cảnh báo mạnh
- ưu tiên sửa choices nếu sửa được
- chỉ DROP nếu lỗi choices làm VQA mất giá trị benchmark

### KEEP nếu:

- question đúng
- choice logic ổn
- `triples_used` đúng hoặc đã được chỉnh hợp lệ

---

## 9. Khi nào nên sửa VQA, khi nào nên drop luôn

### 9.1. Nên sửa nếu:

- lỗi diễn đạt nhỏ
- choices lệch nhẹ nhưng sửa được
- triple còn cứu được bằng `Needs edit`
- đáp án đúng vẫn xác định được rõ

### 9.2. Nên drop nếu:

- câu hỏi sai bản chất
- triple cốt lõi sai và không cứu được
- ảnh quá mơ hồ
- choices hỏng nặng
- không còn đủ căn cứ để giữ VQA làm benchmark

---

## 10. Nguyên tắc sửa triple inline

Nếu verifier chọn **Needs edit**, cần tuân theo nguyên tắc:

### 10.1. Chỉ sửa khi thật sự hiểu triple nên đúng như thế nào

Không sửa theo cảm tính.

### 10.2. Sửa theo hướng tối thiểu cần thiết

Chỉ chỉnh phần sai:

- `subject`
- `relation`
- `target`
- `evidence`
- `source_url`

Không thay cả triple nếu không cần.

### 10.3. Triple revised phải rõ ràng hơn triple cũ

Sau khi sửa, triple mới phải:

- đúng hơn
- dùng được cho VQA hiện tại
- dễ review lại ở page triple

### 10.4. Luôn ghi note ngắn cho lý do sửa

Ví dụ:

- `target sai`
- `relation chưa đúng`
- `evidence cũ không khớp fact`

---

## 11. Những lỗi thường gặp cần chú ý

### 11.1. Câu hỏi đúng nhưng `triples_used` sai

Đây là case rất dễ bỏ sót.
Không vì câu hỏi nghe hợp lý mà bỏ qua fact nền sai.

### 11.2. Choice bị lệch loại

Ví dụ:

- đáp án đúng là một nguyên liệu
- distractor lại là vùng miền hoặc món ăn

Đây là lỗi nghiêm trọng đối với benchmark.

### 11.3. Triple đúng về mặt tri thức chung nhưng không phù hợp ảnh

Ví dụ:

- món ăn nói chung có ingredient đó
- nhưng ảnh hiện tại không thể hiện hoặc không phải món đang hỏi tới

Phải verify trong đúng ngữ cảnh VQA.

### 11.4. Distractor quá vô lý

Nếu 3 lựa chọn nhiễu quá dễ loại, câu hỏi sẽ không phản ánh tốt năng lực reasoning.

### 11.5. Câu hỏi yes/no trá hình

Với một số `qtype` như allergen hoặc dietary, cần tránh giữ các câu hỏi quá gần dạng yes/no nếu mục tiêu benchmark là multiple-choice reasoning.

---

## 12. Quy tắc thống nhất giữa các thành viên

Để tránh mỗi người verify một kiểu, nhóm nên thống nhất:

### 12.1. Cùng dùng một luật KEEP/DROP

Không mỗi người tự hiểu một cách.

### 12.2. Cùng hiểu giống nhau về `Valid / Invalid / Needs edit / Unsure`

Đây là chỗ dễ lệch nhất.

### 12.3. Nếu gặp ca khó, ghi note thay vì tự quyết quá mạnh

Đặc biệt với các triple còn mơ hồ.

### 12.4. Thường xuyên rà soát chéo

Mỗi người nên có một ít mẫu được người khác review lại để hiệu chỉnh cách chấm.

---

## 13. Checklist nhanh trước khi bấm lưu

Trước khi save một VQA, tự hỏi:

1. Tôi đã hiểu ảnh và món trong ảnh chưa?
2. Câu hỏi có đúng với ảnh không?
3. Đáp án đúng có thực sự đúng không?
4. 4 choices có cùng loại không?
5. Mỗi triple trong `triples_used` đã được review chưa?
6. Triple nào cần sửa đã được sửa rõ ràng chưa?
7. Tôi đang KEEP vì câu này thật sự tốt, hay chỉ vì “trông có vẻ ổn”?

Nếu còn lấn cấn ở câu 5 hoặc 6, chưa nên save vội.

---

## 14. Kết luận

Bước verify VQA trong dự án này không chỉ là kiểm tra câu hỏi có “ổn” hay không, mà còn là bước làm sạch phần tri thức được dùng để benchmark vai trò của **ViFoodKG**.

Khi verify, thành viên cần nhớ:

- trọng tâm là **question + choices + triples_used**
- **reason không phải ưu tiên chính**
- nếu triple sai nhưng còn cứu được, dùng **Needs edit**
- nếu câu hỏi mất giá trị benchmark, **DROP**
- luôn ưu tiên tính đúng đắn và tính nhất quán giữa các verifier
