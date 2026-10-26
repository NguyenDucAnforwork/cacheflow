# CacheFlow: tài liệu phỏng vấn Inference Engineer

**Trạng thái:** tài liệu đang được phát triển cùng nghiên cứu V3 từ 2026-10-26. Số liệu V2 dưới đây là baseline đã đo, **không phải bằng chứng đã thắng các method của paper gần đây**. Kết quả method/baseline V3 và profiling sẽ được bổ sung khi kiểm chứng xong. Đọc cùng `docs/PROPOSAL_LOCOMO_AGENTPERF_V2.md`, `docs/V3_RESEARCH_PLAN.md` và `docs/V3_BASELINES.md`.

## 1. Kể project trong hai phút

CacheFlow nghiên cứu cách phục vụ nhiều câu hỏi dùng lại các lịch sử hội thoại dài. Thay vì prefill lại toàn bộ lịch sử mỗi lần, engine có thể tái dùng KV cache của prefix giống hệt về token. GPU nhanh nhưng bộ nhớ hạn chế; CPU RAM giữ được nhiều KV hơn nhưng cần chuyển lại qua PCIe. Project đặt câu hỏi: khi nào tier CPU thực sự giúp, khi nào scheduling có thể tránh việc tính/chuyển dữ liệu thừa, và lợi ích đó còn giữ được khi tính toàn bộ thời gian từ lúc request đến hay không?

Stack baseline hiện tại là Qwen3-1.7B BF16 trên RTX 3090, vLLM làm inference engine, LMCache giữ CPU KV, và gateway Python điều khiển admission. LoCoMo cung cấp hội thoại thật và QA; arrival là workload được xây dựng có công bố seed, không phải trace production. Đóng góp V2 hiện mới là xác nhận cơ chế và phát hiện bẫy đo counter; V3 phải đi xa hơn bằng profiling và so sánh baseline mạnh.

**Câu hỏi: Trong phỏng vấn, nên nói gì là phần mình làm?**

Nói chính xác: xây adapter dữ liệu/prompt có provenance; replay có lịch arrival và capture output; instrument thời gian và source-token counters; xây policy/admission khi có cơ hội đã đo; thiết kế experiment/control/holdout; phân tích latency cùng compute/transfer/quality. Không nhận mình viết vLLM, PagedAttention, LMCache hoặc một thuật toán mới nếu phần đó chưa có.

## 2. Prefill, decode và KV cache

**Câu hỏi: Prefill và decode khác nhau thế nào?**

Prefill xử lý prompt và tạo K/V cho các token đầu vào. Nhiều token có thể được xử lý song song, nhưng attention trên context dài làm chi phí tăng mạnh. Decode tạo từng token mới, mỗi bước đọc lại K/V của lịch sử. Decode thường nhạy với băng thông bộ nhớ và batch size; prefill dài thường sử dụng compute tốt hơn. Đây là mô tả xu hướng: phải profile model, kernel và độ dài cụ thể thay vì mặc định mọi decode đều memory-bound.

**Câu hỏi: KV cache lưu gì, có phải output text không?**

Nó lưu tensor key/value ở các layer attention, không phải câu trả lời hoàn chỉnh. Request sau vẫn phải tính phần suffix khác, sinh output mới và chạy attention. Chỉ token prefix giống hệt, cùng model và các điều kiện cache hợp lệ mới có thể tái dùng trực tiếp. Semantic similarity của hai đoạn văn không đủ để dùng lossless prefix caching.

**Câu hỏi: Tại sao không cache toàn bộ câu trả lời?**

Đó là response caching, một bài toán khác. Hai câu hỏi khác nhau trên cùng lịch sử có thể chia sẻ hàng chục nghìn token KV nhưng cần câu trả lời khác. CacheFlow giữ nguyên inference semantics, tái dùng prefix computation chứ không trả lại một answer cũ.

**Câu hỏi: Tính kích thước KV trên bảng trắng như thế nào?**

Với full attention, xấp xỉ `bytes/token = 2 × layers × KV_heads × head_dim × bytes/element`. Hai lần là K và V. Model này có 28 layer, 8 KV head, head dimension 128 và BF16 hai byte: `2 × 28 × 8 × 128 × 2 = 114,688 byte/token`, tức 112 KiB/token. Một context 32,768 token cần khoảng 3.5 GiB KV, chưa tính weights, allocator, activation, runtime và fragmentation.

**Câu hỏi: Vì sao dùng KV heads chứ không dùng query heads?**

Model dùng grouped-query attention: nhiều query head dùng chung một số KV head. KV storage phụ thuộc số K/V head thật được lưu. Dùng số query head trong công thức sẽ ước lượng quá cao. Tensor parallelism, KV replication, cache quantization hoặc hybrid attention có thể làm công thức phân bổ theo GPU khác đi.

**Câu hỏi: RTX 3090 24 GiB mà thí nghiệm chỉ cho KV 4/8 GiB có vô lý không?**

Đây là capacity experiment có chủ đích. Ta giữ hardware/model cố định, thay allocated KV budget để kiểm tra điều kiện residency. Không được kết luận workload cần offload khi toàn bộ VRAM khả dụng được cấp cho KV. V2 đo actual capacity 37,440 token ở 4 GiB và 74,896 ở 8 GiB, thay vì chỉ dùng phép chia nominal.

**Câu hỏi: KV cache và prefix cache có phải hai bộ tensor hoàn toàn tách biệt?**

Không nhất thiết. Engine có thể dùng cùng pool block, với reference counts và metadata để phân biệt block đang được request sử dụng với block đã hoàn tất nhưng còn giữ cho reuse. Vì vậy request kết thúc không đồng nghĩa dữ liệu bị xóa; usage của active blocks bằng zero cũng không chứng minh không còn cached prefix.

## 3. Paging, locality và bộ nhớ

**Câu hỏi: PagedAttention giải quyết vấn đề gì?**

Nó cho phép sequence dùng các block vật lý không liên tục, ánh xạ qua block table. Điều này giảm nhu cầu cấp phát một vùng liên tục lớn và hỗ trợ chia sẻ block prefix, copy-on-write khi cần. Nó không tự tạo thêm bandwidth, không làm mọi context cùng fit, và không loại bỏ chính sách eviction/admission.

**Câu hỏi: Vì sao có hit rồi vẫn phải recompute?**

Cần phân biệt hit tại lần lookup, block được giữ đủ lâu để allocation/scheduling thành công, và token cuối cùng thực sự được dùng từ cache. Scheduler có thể thử lại một request nhiều lần. Một counter cộng hit mỗi lần probe có thể lớn hơn tổng input của trace. V2 có trường hợp lookup-hit count cao nhưng actual cached prompt tokens thấp hơn rất nhiều.

**Câu hỏi: Khi cache chỉ còn suffix của một prefix, tại sao chưa chắc dùng được?**

Exact prefix matching thường dựa trên chuỗi block hash có quan hệ với prefix trước nó. Một đoạn cuối còn trong RAM không tự đảm bảo toàn bộ K/V trước đó còn hợp lệ hoặc được engine định vị để resume. Phải xem cấu trúc cache và API cụ thể; không suy từ số byte còn nằm trong pool thành số token có thể dùng.

**Câu hỏi: Working-set size có đủ dự đoán latency không?**

Không. Nó là tín hiệu áp lực, còn latency phụ thuộc reuse distance, arrival burst, request đang chạy, shared blocks, output length, eviction order và queueing. Hai seed có cùng lượng first-pass prefill vẫn có p95 khác đáng kể. Trong V2 holdout, một arm còn tận dụng GPU reuse nhiều hơn arm kia, nên CPU-restored tokens không luôn bằng avoided compute.

**Câu hỏi: Internal và external fragmentation là gì trong bối cảnh này?**

Internal fragmentation là token chưa dùng trong block cuối nhưng block vẫn chiếm chỗ. External fragmentation là còn tổng dung lượng trống nhưng không có vùng liên tục phù hợp; paging giảm vấn đề này. Ngoài ra còn có prefix opportunity loss do chỉ cache/match được block đầy: nó là mất cơ hội reuse, không hoàn toàn đồng nghĩa waste bytes trong allocator.

## 4. CPU ↔ GPU: latency, bandwidth, overlap

**Câu hỏi: Tại sao CPU KV giúp dù CPU chậm hơn GPU?**

Ta thường không chuyển attention computation sang CPU. CPU giữ tensor đã tính; khi cần, dữ liệu được đưa về GPU. Nếu transfer cộng lookup/scheduling nhanh hơn recompute prefix, offload có thể giảm TTFT. Khi prefix vẫn ở GPU, CPU tier có thể chỉ thêm lookup/backup overhead.

**Câu hỏi: Viết điều kiện load-vs-recompute đơn giản thế nào?**

So sánh `T_load ≈ fixed_overhead + bytes/bandwidth + queue_and_sync` với thời gian recompute được đo theo độ dài context/suffix và batch. Nhưng tổng latency không nhất thiết là tổng các phase vì có overlap. Một quyết định tốt cho request riêng lẻ còn có thể làm request khác chậm do chiếm PCIe, SM hoặc KV slots.

**Câu hỏi: Tại sao transfer nhỏ không đạt bandwidth lý thuyết?**

Mỗi transfer có chi phí launch, scheduling và synchronization. Từ Little's Law, throughput I/O lý tưởng liên hệ `X ≈ concurrency × transfer_size / latency`. Nhiều mảnh rất nhỏ có thể bị giới hạn bởi overhead thay vì PCIe throughput. Coalescing hoặc GPU-assisted scatter/gather có thể giúp, nhưng tốn kernel resources và phải bảo toàn mapping dữ liệu.

**Câu hỏi: Pinned memory là gì?**

Đó là host memory được page-lock để DMA có thể truy cập ổn định. Pageable memory có thể cần staging copy. Pinned memory giúp asynchronous H2D/D2H nhưng không miễn phí: dùng quá nhiều làm giảm RAM linh hoạt của OS và có thể ảnh hưởng hệ thống khác. Cần theo dõi allocated pool, resident memory và actual payload riêng.

**Câu hỏi: `non_blocking=True` có bảo đảm overlap không?**

Không. Còn phụ thuộc pinned memory, streams, hardware copy engines, dependency events, tensor lifetime và việc có công việc độc lập để overlap. Một lệnh async sau đó lập tức synchronize vẫn có thể tạo critical-path stall. Phải nhìn timeline hoặc CUDA-event timing, không chỉ nhìn tên API.

**Câu hỏi: CUDA stream và event giúp gì?**

Stream biểu diễn thứ tự công việc; event biểu diễn dependency giữa stream hoặc điểm đo. Transfer stream có thể nạp dữ liệu trong lúc compute stream xử lý phần độc lập, nhưng compute phải chờ event khi thực sự cần KV. Đồng bộ toàn device dễ lập trình nhưng có thể xóa overlap; thiếu đồng bộ gây race/corrupt output.

**Câu hỏi: Vì sao phải quan tâm NUMA/PCIe topology?**

Host memory nằm xa PCIe root complex hoặc thread chạy trên NUMA node khác có thể tăng latency và giảm bandwidth. GPU marketing bandwidth không phải bandwidth end-to-end từ allocation cụ thể đến GPU. Ghi lại topology và pinning khi đo; container có thể hạn chế quyền quan sát hoặc affinity.

**Câu hỏi: LMCache L1 read count có chứng minh có H2D transfer không?**

Không. Ở stack này, L1 là CPU tier. V2 GPU-fit control vẫn có 2,224 L1 read chunks nhưng consumed external KV bằng zero. Lifecycle/read-lock activity, potential cache hits, chunks actually loaded và engine-consumed external tokens là các stage khác nhau. Đây là câu chuyện phỏng vấn tốt về cách phát hiện một measurement bug trước khi kết luận method tốt.

## 5. Queueing và admission

**Câu hỏi: Gateway admission khác engine scheduling thế nào?**

Gateway quyết định request nào gửi vào engine và lúc nào. Engine còn quyết định prefill/decode batch, KV allocation, chunked prefill, preemption và kernel execution. Gateway không có quyền giả định nó kiểm soát được intra-request H2D/recompute nếu chưa có API đã kiểm chứng.

**Câu hỏi: Vì sao giảm engine TTFT có thể là một kết quả sai?**

Nếu gateway giữ request một giây rồi mới dispatch, engine có thể báo nhanh hơn dù client chậm hơn. Primary metric phải là scheduled arrival đến first nonempty generated text. Báo thêm ingress preparation, admission wait, engine queue và execution để giải thích, không thay thế metric end-to-end bằng phase đẹp nhất.

**Câu hỏi: Max inflight có phải max GPU batch size không?**

Không. Inflight của gateway gồm request đang chờ trong engine và đang execute. Engine có `max_num_seqs` và token budget riêng. Gateway cap 16 với engine max sequences 4 có thể chỉ tạo thêm queue, hoặc cho engine thêm lựa chọn để tận dụng shared prefixes. Cap quá thấp cũng có thể giảm batching/throughput.

**Câu hỏi: Vì sao FIFO là baseline cần nhưng chưa đủ mạnh?**

Nó cung cấp đối chứng dễ hiểu, nhưng có thể bỏ lỡ locality hoặc bị một cấu hình cap xấu làm yếu đi. Một method mới cần so với FIFO đã tune, cache-aware ordering như LPM, grouping có aging, và implementation engine mạnh liên quan. Thắng một default FIFO yếu chưa chứng minh đóng góp nghiên cứu.

**Câu hỏi: Tại sao fixed 200-ms delay-hit policy thất bại trong V2?**

Trong các E1 đã đo, FIFO và DHAS có cùng lượng prefill/cache work; vLLM đã tái dùng block theo cơ chế nội bộ trong những điều kiện đó. TTFT có thay đổi nhỏ nhưng đổi dấu theo run/order. Do đó không có bằng chứng delay tạo thêm reuse, và không được xây B5 chỉ để tối ưu tiếp một cơ chế chưa có opportunity.

**Câu hỏi: Làm sao tránh starvation khi ưu tiên cache hit?**

Có thể dùng aging, bound cho số request/cohort liên tiếp, deadline hoặc ưu tiên oldest tại đầu mỗi batch. Nhưng một bound trong policy không tự là bound end-to-end khi queue quá tải. Cần báo cả p95/p99, max wait và nhóm low-reuse, rồi phân biệt intentional deferral với capacity wait.

## 6. Benchmark và correctness

**Câu hỏi: Open-loop và closed-loop khác gì?**

Open-loop giữ lịch arrival độc lập với tốc độ server, cho thấy queue buildup khi offered load vượt capacity. Closed-loop thường duy trì concurrency, gửi request mới khi request cũ xong; server chậm làm arrival giảm. Cả hai có ích nhưng không trộn throughput/latency như cùng một workload. Think-time conversation replay là một mô hình khác cần công bố dependency.

**Câu hỏi: Vì sao percentile của 30 request cần thận trọng?**

p95 được quyết định bởi rất ít request ở đuôi. Repeating ba seed không biến 30 QA thành 90 mẫu dữ liệu nội dung độc lập. Đơn vị uncertainty cho paired experiment là run. Cần nhiều run hoặc steady-state trace dài hơn để kiểm tra tail/SLO, đồng thời giữ failures/timeouts trong báo cáo.

**Câu hỏi: Warmup/reset đúng cần làm gì?**

Chờ không còn active/queued request; dùng cùng warmup cho mọi arm; chờ async stores hoàn tất; clear CPU cache và reset GPU prefix cache; kiểm tra health/gauge và ghi PID. Nếu đổi engine/config, công bố cold restart; không gọi đó là same-engine crossover. Prefill của cold prefixes là một kiểm tra thực nghiệm bổ sung cho reset.

**Câu hỏi: Temperature zero có bảo đảm output y hệt không?**

Không. Batch shape, kernel/reduction order và sai khác số học có thể đổi argmax ở vị trí gần hòa. Hash mismatch chứng minh text khác, không tự chứng minh semantic corruption. Cần giữ text, chấm theo evaluator cố định và xem trường hợp cụ thể; cũng không dùng lý do nondeterminism để bỏ qua một regression thật.

**Câu hỏi: Lossless KV offload có bảo đảm QA quality không đổi không?**

Lossless mô tả cách lưu tensor, không phải một theorem về output của toàn pipeline. Phải bảo đảm đúng model, token positions, dtype, block mapping, synchronization và request isolation. Sau đó vẫn cần audit output/score vì execution shape có thể khác. V2 có score/hash differences nên không claim blanket equivalence.

**Câu hỏi: Vì sao raw-template V2 có F1 thấp?**

Nhiều generation lặp câu và chạm cap 64 token; original evaluator chấm toàn bộ generation nên verbosity/repetition làm precision thấp. Đây là lỗi phù hợp prompt/model/protocol cần công bố. Không được cắt đáp án sau khi nhìn gold để tăng score rồi giữ cùng tên protocol. V3 dùng chat template và concise instruction đã freeze trước comparison mới.

**Câu hỏi: Gold leakage được tránh thế nào?**

Prompt chỉ chứa conversation text, public caption, chronology và câu hỏi. Gold answer và evidence annotation dùng ngoài inference cho grading/checkpoint construction. P-SESSION chỉ lộ history tới checkpoint chứa evidence hợp lệ; full-context QA và adapted checkpoint serving được chấm/report riêng.

## 7. Profiling: cách trả lời có chiều sâu

**Câu hỏi: Bắt đầu profiling từ đâu?**

Đầu tiên xác định symptom: queue tăng, TTFT tăng, GPU idle hay transfer lớn. Tách arrival → receive → tokenize/hash → admission → engine queue → prefill/restore → first token → decode. Thu resource/counter để có giả thuyết, sau đó dùng timeline/events để xác định critical path. Chạy lại unprofiled để kiểm tra overhead của profiler.

**Câu hỏi: CPU wall-clock timing đủ cho CUDA chưa?**

Không, API có thể trả về trước khi GPU xong. CUDA events hoặc GPU-stream callbacks giúp đo execution/transfer thật. Nhưng chúng dùng clock domain khác client monotonic time; cần calibration/correlation và request/session IDs. Thời gian bus subscriber xử lý event không phải thời gian event xảy ra.

**Câu hỏi: Tổng CUDA time có bằng end-to-end latency không?**

Không. Các kernel/copy có thể overlap, CPU có thể stall, queue có thể đợi, và profiler có nhiều stream. Cộng toàn bộ duration có thể double-count overlap. Cần nhìn critical path/union intervals và phân loại phase, đồng thời giữ latency client làm primary outcome.

**Câu hỏi: Chọn ablation thế nào?**

Mỗi ablation bỏ một cơ chế cụ thể: ordering, residency budget, cost model, aging hoặc overlap. Dùng cùng trace/reset và không lén thay output length. Nếu baseline cap tốt đã tạo toàn bộ gain thì phải nói đóng góp chỉ là cap selection, không nhận phần lợi ích đó cho một policy phức tạp hơn.

## 8. Paper/baseline: nói đúng phạm vi

Strata (OSDI 2026) liên quan trực tiếp CPU/GPU I/O và cache-aware scheduling; Cake (ICML 2025) liên quan compute/load overlap; LPC (NeurIPS 2025) là learned eviction; EpiCache (ICML 2026) là episodic compression cho long-conversation QA. Xem nguồn gốc và trạng thái implementation tại `docs/V3_BASELINES.md`.

**Câu hỏi: Nếu không chạy được code paper thì làm gì?**

Ghi chính xác commit, dependency, hardware requirement và lỗi thử chạy. Có thể port một cơ chế, nhưng phải gọi là adaptation và mô tả phần bị bỏ. Không lấy số published trên H100/H200 để làm baseline trực tiếp cho RTX 3090. Nếu baseline cần training, không dùng một predictor random rồi gọi đó là method của paper.

**Câu hỏi: Contribution cần chứng minh điều gì để mạnh hơn V2?**

Cần một cơ chế có thể giải thích bằng profiling, vượt baseline mạnh/tuned ở metric end-to-end hoặc SLO throughput, còn giữ được chất lượng và không che tail/low-reuse regression. Cần confirmation chưa dùng để tune, repeated runs và ablation. Một observation đúng hoặc một speedup so với FIFO chưa tự đáp ứng tiêu chuẩn này.

## 9. Kết quả V3 và phần diễn tập nâng cao

Đang triển khai. Phần này sẽ cập nhật method cuối, timeline thật, table baseline, counterfactual/ablation và Q&A bảo vệ kết quả sau khi có bằng chứng. Không dùng trạng thái đang chạy như một kết quả đã đạt.

## 10. Profiling V3 đã quan sát: bài học có số liệu

Các số dưới đây là diagnostic/screen, chưa phải kết luận contribution cuối.

**Câu hỏi: Bạn từng gặp profiler làm sai kết luận chưa?**

Có. Cùng trace dev 60 QA và cùng cap 16, run bật PyTorch profiler có p95 khoảng 31.03 giây; run unprofiled khoảng 3.57 giây. Nếu xem run có profiler là baseline thật, ta sẽ tưởng queueing là vấn đề lớn hơn thực tế rất nhiều. Profile CUDA window thu được khoảng 8.32 giây, model-kernel union khoảng 6.43 giây; phần này chủ yếu là đầu trace/cold phase. Vì vậy không dùng nó đại diện toàn bộ steady state. Trace được giữ để xem kernel/dependency; latency chính phải lấy từ unprofiled comparisons.

**Câu hỏi: Bạn kiểm tra bandwidth đường CPU–GPU thế nào trước khi tối ưu?**

`nvidia-smi` báo link tối đa thực tế trên host này là Gen3 x16, dù tên card có thể khiến mình nghĩ tới Gen4. Từ encoding PCIe Gen3, băng thông lý thuyết một chiều x16 xấp xỉ 15.75 GB/s, trước protocol overhead. Lightweight LMCache GPU-stream events ghi 56 retrieve events, khoảng 121.7 GB payload, 10.73 giây duration cộng dồn; median event throughput khoảng 11.35 GB/s. Đây là băng thông transfer, không phải throughput request và không phải toàn bộ latency request. Tổng thời gian event có thể overlap, nên không cộng thẳng vào E2E TTFT.

**Câu hỏi: Tại sao không kết luận cần viết kernel H2D nhanh hơn ngay?**

Băng thông đã đạt phần đáng kể giới hạn link; cải thiện kernel có trần lợi ích. Giảm byte phải chuyển bằng residency/locality có thể có headroom lớn hơn, nhưng có nguy cơ tăng queue wait hoặc starvation. Screen cho thấy có policy giảm transfer mà p95 vẫn xấu hơn. Cần tối ưu outcome cuối, không chỉ một resource counter.

**Câu hỏi: Model lớn hơn làm capacity planning thay đổi gì?**

Model 4B đang chuẩn bị có 36 layer thay vì 28. Với 8 KV head, head dimension 128 và BF16, KV là 144 KiB/token; context 32K cần 4.5 GiB KV. Vì vậy không được bê nguyên budget 4 GiB từ model 1.7B rồi gọi OOM là method failure. Model và checkpoint phải được pin/verify trước khi dùng; tại checkpoint này weights 4B vẫn đang tải, chưa có kết quả GPU của nó.

**Câu hỏi: Một baseline cache-aware mạnh có thể vẫn làm hại fairness như thế nào?**

LPM có thể ưu tiên request khớp prefix vừa dùng, giảm migration từ CPU nhưng làm nhóm khác đợi. Cap 1 có thể giúp locality song làm mất batching. Bundle theo wave giúp một số shared-prefix requests nhưng có thể phải đợi request sinh dài nhất trong wave. Cần cùng cap, cùng engine và cùng trace để phân biệt lợi ích ordering với lợi ích throttle; kiểm tra p95/p99 và từng nhóm request, không chỉ median.

### 10.4. Vì sao “request gần nhất” không đồng nghĩa với KV đang ở GPU?

**Hỏi:** Dùng conversation vừa phục vụ để chọn request tiếp theo có đủ chính xác không?

**Đáp:** Không. Trong thời gian một request decode, những request khác có thể làm các block cũ bị thu hồi. Một conversation cũng có thể chỉ còn một phần prefix trên GPU. LPM-hint của baseline dùng lịch sử request nên chỉ là tín hiệu gần đúng. Prototype V3 đang chuyển sang sự kiện `BlockStored`, `BlockRemoved`, `AllBlocksCleared` mà vLLM phát ra. Gateway tạo cùng chuỗi hash theo block 16 token và đếm prefix liên tiếp còn trong index. Thông tin này vẫn có độ trễ truyền sự kiện; nó là ước lượng phục vụ admission, không phải quyền sở hữu hay khóa block trong allocator.

**Hỏi:** Hash của gateway làm sao khớp hash của engine?

**Đáp:** Phải khớp cả seed của block đầu, thuật toán, cách serialize, kích thước block và các khóa phụ. Bản vLLM đã pin dùng `sha256(pickle((parent_hash, token_ids_tuple, extra_keys)))` cho cấu hình text-only này. Cả hai tiến trình đặt `PYTHONHASHSEED=0`; hash gốc được tạo từ chuỗi `"0"`. Gateway đã được đối chiếu trực tiếp với hàm vLLM trên sáu block nối tiếp. Không được suy ra rằng contract này tự động đúng cho LoRA, multimodal, cache salt hay bản vLLM khác.

**Hỏi:** Nếu subscriber bỏ lỡ một sự kiện thì sao?

**Đáp:** Nếu bỏ lỡ sự kiện remove, gateway có thể tưởng một block đã bị đuổi vẫn còn trên GPU. Mỗi batch có số thứ tự; khi phát hiện khoảng trống, prototype xóa index và chuyển sang FIFO. Chỉ một sự kiện clear đáng tin cậy mới thiết lập lại trạng thái biết chắc từ cache rỗng. Khi gateway mới khởi động, trạng thái mặc định là chưa biết. Health endpoint phải cho thấy subscriber còn chạy, số gap và tuổi của sự kiện cuối. Kết quả đo dùng residency phải kiểm tra các điều kiện này, thay vì thấy tiến trình sống là cho rằng observer hoạt động.

**Hỏi:** Vì sao cần đếm số bản sao của cùng một hash?

**Đáp:** Hai block vật lý có thể biểu diễn cùng nội dung prefix. Một remove chỉ làm mất một bản sao. Nếu dùng tập hợp rồi xóa hash ngay, index sẽ báo miss dù vẫn còn bản sao khác. Prototype dùng bộ đếm tham chiếu; chỉ bỏ hash khi không còn bản sao được quan sát.

### 10.5. Admission theo bộ nhớ khác giới hạn concurrency như thế nào?

**Hỏi:** Cap bốn request có đảm bảo vừa GPU không?

**Đáp:** Không. Bốn request cùng prefix có thể dùng chung phần lớn KV; hai request khác nhau dài 25 nghìn token có thể cần hơn 50 nghìn token KV. GPU KV 4 GiB của model 1.7B trong cấu hình này chỉ chứa khoảng 37.440 token. Vì thế số request là một chỉ báo quá thô.

**Hỏi:** Prototype ước lượng bộ nhớ ra sao?

**Đáp:** Lấy hợp các hash block đầy đủ của các request đang active, mỗi hash chỉ tính một lần. Sau đó cộng riêng đuôi prompt chưa đủ block, ngân sách token sinh và một block dự phòng cho từng request, làm tròn theo block. Đây là dự phòng bảo thủ ở cấp gateway; allocator thật còn có null block, copy-on-write và thời điểm giải phóng bất đồng bộ. Prototype dùng 37.424 token thay vì 37.440 để chừa null block. Engine vẫn chịu trách nhiệm bảo vệ bộ nhớ và tính đúng của attention.

**Hỏi:** Khi request đầu hàng không vừa thì phải làm gì?

**Đáp:** Có thể cho một request phía sau dùng chung prefix với nhóm đang active đi trước, nếu dự phòng bộ nhớ vẫn vừa. Nhưng phải giới hạn số lần vượt hàng. Prototype cho phép tối đa bốn lượt rồi ngừng backfill để các request đang chạy hoàn thành và request cũ được phục vụ. Khi không có active request, luôn cho request cũ nhất tiến lên; nếu chỉ chờ một ước lượng vừa bộ nhớ, một request dài đơn lẻ có thể bị kẹt vô hạn.

**Hỏi:** Đã chứng minh đây là contribution chưa?

**Đáp:** Chưa. Đây là giả thuyết đang được kiểm chứng. Cần thắng FIFO đã tune, LPM có cùng thông tin residency và bundle-wave; cần kiểm tra riêng memory packing, thông tin cache và guard chống starvation. Ngoài p95 còn phải đo p99, độ trễ theo conversation, lượng KV CPU thực sự được tiêu thụ và chất lượng output. Một heuristic giảm transfer nhưng làm hàng đợi lâu hơn không thỏa RQ2.

**Bài học từ lỗi đo thực tế của V3:** Hàm hash nội bộ đã khớp nhưng vẫn chưa đủ: engine mặc định chuyển hash ra ngoài thành số nguyên 64-bit để tương thích cũ. Gateway giữ bytes nên mọi lookup đều miss, dù sự kiện đến đầy đủ. Những lượt screening này được đánh dấu diagnostic và không dùng để kết luận lợi ích từ residency. Cấu hình sửa buộc engine phát bytes bằng `VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=0`; subscriber kiểm tra cả kiểu dữ liệu lẫn hash của một payload store thật. Đây là ví dụ vì sao “metric có số” và “tiến trình không lỗi” không chứng minh phép đo đúng.

## 11. Thiết kế thí nghiệm và phản biện kết quả

**Hỏi: Ba seed, mỗi seed 60 QA, có phải là 180 câu hỏi độc lập không?**

Không. Cùng 60 QA được phát theo ba lịch arrival khác nhau. Seed kiểm tra độ nhạy với thứ tự và khoảng cách request, không mở rộng độ đa dạng câu hỏi. Khi so latency, đơn vị lặp quan trọng là cặp lượt chạy cùng trace; khi báo chất lượng phải ghi rõ chỉ có 60 QA khác nhau. Lấy 180 hàng làm 180 mẫu độc lập sẽ phóng đại độ chắc chắn.

**Hỏi: Vì sao không chỉ lấy trung bình tất cả request rồi bootstrap?**

Các request trong một run ảnh hưởng cache và hàng đợi của nhau. Một request chậm có thể làm nhiều request sau chậm theo. Bootstrap từng request như thể độc lập sẽ bỏ qua tương quan đó. Với ba run, nên trình bày từng seed, mức biến thiên và cơ chế work-saving; không tuyên bố ý nghĩa thống kê mạnh chỉ vì có hàng trăm hàng log. Muốn confidence interval đáng tin hơn cần thêm run độc lập và workload đa dạng.

**Hỏi: Lấy 20 QA đầu mỗi conversation có nhược điểm gì?**

Thứ tự QA gốc có thể liên quan đến category hoặc độ khó; đây không phải mẫu ngẫu nhiên đại diện toàn LoCoMo. Dev subset giúp screening có chi phí kiểm soát, nhưng kết luận phải giữ đúng phạm vi. Để tuyên bố benchmark tổng quát cần đánh giá toàn bộ phần fit hoặc một mẫu được phân tầng, đóng băng trước khi xem kết quả. Conversation-disjoint holdout kiểm tra một loại tổng quát hóa khác với thay seed trên cùng câu hỏi.

**Hỏi: Throughput đo từ replay open-loop có phải công suất tối đa của server không?**

Không nhất thiết. Nếu arrivals thưa, server chủ yếu chờ request; throughput khi đó bị giới hạn bởi lịch gửi. Nếu arrivals dồn và queue lớn, makespan phản ánh năng lực xử lý rõ hơn nhưng vẫn phụ thuộc trace hữu hạn. Vì vậy cần nhiều offered load, báo queue growth, TTFT và thời gian hoàn tất trace, đồng thời phân biệt achieved throughput với saturated throughput.

**Hỏi: Chất lượng baseline V3 hiện thế nào?**

Audit chính thức của chín lượt baseline dev (ba policy × ba seed, cùng 60 QA) cho F1 khoảng 0,096–0,103. Số output chạm cap 96 token chỉ 0–1/60, cải thiện vấn đề câu trả lời dài của prompt V2, nhưng điểm tuyệt đối vẫn thấp. Không thể gọi đó là chất lượng tốt hoặc kết luận tương đương chỉ từ các giá trị trung bình gần nhau. Cần xem các output thay đổi, điểm theo category và chạy model mạnh hơn với cùng protocol.

**Hỏi: Nếu LPM thật giảm transfer mà p95 tăng thì giải thích thế nào?**

LPM tối ưu mức trùng prefix tại thời điểm chọn, không trực tiếp tối ưu thời gian chờ của request lâu nhất. Nó có thể phục vụ liên tiếp một conversation và làm conversation khác chờ, hoặc cho nhiều request cùng tràn vào engine khiến dự đoán residency mất hiệu lực sau đó. Cần nhìn cả admission wait, engine queue wait, active-memory union, transfer và latency theo conversation. Đó là lý do baseline LPM phải được đo thật và candidate cần guard; không thể suy ra giảm byte chuyển đồng nghĩa giảm tail latency.

## 12. Đối chiếu với một engine độc lập

**Hỏi: Đã chạy được baseline của hệ thống khác trên chính dữ liệu này chưa?**

Đã chạy upstream SGLang0.5.14 với HiCache/LPM trên cùng model 1.7B, prompt V3 và dev trace 60 QA. Một run hợp lệ đã kiểm tra token prompt, capture output và native metrics; p95 khoảng 6,94 giây ở seed101. Cấu hình có decode CUDA graphs, cache GPU37.440 token và CPU16 GiB. Đây là kết quả dev ban đầu, còn cần thêm seed và tune backend. Không gọi nó là toàn bộ Strata: việc dùng HiCache không tự động tái hiện mọi thành phần scheduler trong paper.

**Hỏi: Vì sao không so trực tiếp counter giữa SGLang và vLLM?**

Tên và nơi tăng counter khác nhau. vLLM có source-token accounting cho phần KV thực được engine sử dụng; HiCache có counter số token được yêu cầu promote từ host và timer quanh hàm `load_back`. Trong source đã kiểm tra, hàm này enqueue copy bất đồng bộ rồi trả device indices. Timer CPU quanh hàm có thể rất ngắn dù DMA vẫn chạy sau đó. Vì vậy không lấy số byte chia timer này để tuyên bố băng thông PCIe khổng lồ. Cần CUDA events/timeline đúng stream và phải xác minh điểm đồng bộ hoàn tất.

**Hỏi: So hai engine cần kiểm soát thêm những gì?**

Ngoài model/prompt/token budget/arrival/cache capacity, phải ghi attention backend, graph mode thực đã resolve, chunked-prefill size, concurrency, dtype, cache layout, host write policy và phiên bản kernel. Ở baseline này, upstream SGLang tự tắt prefill graphs với Triton dù decode graphs bật. Hai engine cũng có thể sinh output khác nhau ở temperature0; phải chấm câu trả lời thay vì mặc định số học floating-point và batching hoàn toàn bất biến.

**Hỏi: Một phiên bản thư viện cài thành công đã chứng minh baseline khả dụng chưa?**

Chưa. V3 đã gặp wheel native đòi cuBLAS13 trong môi trường torchCUDA12.8, rồi thiếu dependency của HTTP/audio entrypoint dù chỉ phục vụ text. Các cổng kiểm tra theo thứ tự là import native → nạp model → cấp KV/CPU pools → sinh token → replay đúng token/output → audit metrics/quality. Lượt replay đầu HiCache còn gặp lỗi sampler khi một tiến trình con thoát; nó được giữ làm diagnostic và chạy lại với ID mới. Không lấy việc mở cổng HTTP thay cho kiểm chứng phục vụ thật.

### 12.1. Kiểm tra với model mạnh hơn

Qwen3-4B đã được tải ở revision cố định và kiểm SHA cả ba shard. Lượt FIFO đầu trên cùng 60 QA dev của prompt V3 cho F1 **0,3147**, với 3/60 output chạm cap96; đây là kiểm tra chất lượng tốt hơn model1.7B (~0,10), không phải kết quả toàn LoCoMo. Cấu hình 4B dùng KV6GiB, CUDA graphs và maxseq16. Model4B có36 layer,8 KV head, head dimension128: `2 ×36 ×8 ×128 ×2 =147.456 byte/token`, tức144KiB/token. Context32K cần4,5GiB chỉ cho KV, vì thế không thể giữ nguyên budget4GiB của1.7B rồi tuyên bố cùng maximum context.

**Hỏi: Đổi sang model4B có đủ để gọi contribution mạnh hơn chưa?**

Không. Nó giúp kiểm tra rằng workload có câu trả lời hữu ích hơn và cơ chế có tổng quát qua model hay không. Contribution scheduling vẫn cần thắng baseline được tune trên cùng model4B, giữ đúng prompt/output budget, kiểm soát p95/p99 và chấm các output thay đổi. Thời gian giữa model1.7B và4B không phải phép so nhân quả chỉ thay số tham số, vì KV geometry và budget cũng thay đổi. Những kết quả đầu vẫn là dev screening; confirmation chưa được chạy.

## 13. CPU trong gateway có thể làm hỏng một thí nghiệm GPU như thế nào?

**Hỏi: Gateway chỉ admission, tại sao lại ảnh hưởng mạnh đến tail latency?**

Gateway dùng một asyncio event loop. Đoạn tính toán Python đồng bộ chạy lâu sẽ giữ event loop, khiến việc đọc body, xử lý socket, chuyển tiếp token và giải phóng ticket cùng phải đợi. Nếu mỗi waiter thức dậy rồi tính lại một quyết định giống nhau, chi phí còn nhân với số request đang chờ. Đẩy việc chờ ra gateway không loại bỏ chi phí đó: arrival-TTFT phía client vẫn tính tất cả.

**Hỏi: Profiling thực tế đã tìm thấy gì?**

Một CPU microprofile với kích thước prefix lấy từ trace,4 active/50 queued/50 recent cho thấy việc dựng hợp block của cùng nhóm active lặp lại cho từng ứng viên chiếm phần lớn thời gian. Microbenchmark không bật profiler đo bản cũ khoảng12,06ms cho một quyết định; bản tái dùng active union khoảng4,57ms; quyết định lặp lại trên trạng thái không đổi khoảng0,006ms. Nội dung block trong microbenchmark là tổng hợp, không phải một lượt QA end-to-end. Không đem tỷ số đó quảng cáo là speedup của toàn hệ thống.

**Hỏi: Tối ưu cụ thể là gì?**

Tạo tập hợp `A` của block active một lần. Dự phòng thêm cho request mới là số block của nó chưa thuộc `A`, cộng đuôi prompt/output/safety. Dùng phép hiệu tập hợp trong C của Python thay cho dựng lại toàn bộ union hoặc một generator Python chạy qua từng block. Cache lựa chọn khi queue order, active IDs và bypass counts không đổi. Với LPM/residency, khóa cache phải có cả sequence của sự kiện KV; packing không dùng số GPU hit nên không cần vô hiệu hóa chỉ vì một sự kiện cache mới.

**Hỏi: Chứng minh tối ưu không âm thầm đổi policy như thế nào?**

Đối chiếu với source prototype ở commit cố định trên270 lần chọn, bao gồm queue, active set, guard, trạng thái residency và các policy khác nhau. Kiểm tra riêng công thức incremental reservation bằng100 trạng thái có prefix chia sẻ, block khác nhau, block lặp và output budget khác nhau. Các test còn kiểm tra cache phải vô hiệu khi queue/active/guard hoặc KV-event sequence thay đổi. Đây là kiểm chứng logic; GPU repetitions sau đó mới kiểm tra lợi ích vận hành.

**Hỏi: Vì sao giữ cả CPU time và wall time của decision?**

`thread_time_ns` đo CPU của thread chạy scheduler; `perf_counter_ns` đo thời gian thực trôi qua, gồm cả lúc thread bị hệ điều hành ngắt. Hai con số trả lời hai câu hỏi khác nhau. Decision-cache hit count cũng cần thiết: gọi `_choose` hàng nghìn lần không có nghĩa đã tính hàng nghìn quyết định đầy đủ. Không dùng số lần gọi làm số request được admit.

**Hỏi: Các lỗi HTTP502 ban đầu được xử lý ra sao?**

Một số arm cap16 trả ReadError từ upstream; các run đó được đánh dấu invalid, giữ nguyên toàn bộ request lỗi và không so percentile chỉ trên request thành công. Telemetry mới giữ loại exception, cause và nội dung lỗi HTTP. Sau tối ưu, hai lượt chẩn đoán cùng packing16 đều60/60 thành công dù giữ128 hay0 kết nối upstream. Vì thế chưa chứng minh keep-alive là nguyên nhân duy nhất. Các lượt chính tiếp theo chuẩn hóa kết nối local mới và không retry; request lỗi sẽ làm ma trận thông thường dừng.

**Hỏi: Có nên tự động retry để đủ60/60 không?**

Không dùng retry ẩn trong benchmark. Một POST bị mất kết nối có thể đã được engine nhận; gửi lại có thể tạo công việc thừa, thay đổi queue/cache hoặc trùng request ID. Nếu sau này nghiên cứu retry, phải công bố policy, tính cả thời gian/compute của mọi attempt và giữ nguyên lỗi gốc. Trong protocol hiện tại, lỗi được báo và lượt chạy bị loại khỏi kết luận hiệu năng.

**Hỏi: Guard bốn lượt có đảm bảo request chờ không quá200ms không?**

Không. Nó giới hạn số request phía sau được vượt head trong policy packing. Sau ngưỡng đó, policy chờ các request active hoàn thành để head tiến lên. Thời gian còn phụ thuộc decode, tải GPU và độ trễ upstream; không có hard latency bound chỉ từ số lượt bypass. Tham số200ms thuộc baseline DHAS, giới hạn một loại deferral khi có slot, chứ cũng không thể xóa queue do cap hoặc overload. Mọi kết luận dùng arrival-TTFT và thời gian chờ thực, không dùng tên tham số để thay cho SLA.

**Hỏi: Có lỗi prompt/evaluator nào chỉ xuất hiện khi mở rộng toàn bộ QA không?**

Có. Official evaluator của category5 chấm abstention bằng cụm “no information available” hoặc “not mentioned”. Prompt V3 yêu cầu “I don't know”, nên có thể bị chấm sai dù model nhận biết không có thông tin. Những dev cohort60 QA hiện tại không có category5; điểm F1 của chúng không được suy ra cho cả benchmark. Protocol V4 được chuẩn bị trước formal freeze, đổi cùng một hướng dẫn toàn cục thành “No information available.”, giữ nguyên nội dung câu hỏi, context và output budget. Không thay câu trả lời sau khi sinh hoặc đổi evaluator để làm đẹp điểm; các baseline phải chạy lại cùng protocol mới.

## 14. Kết quả 4B trên HiCache và cách giải thích tradeoff

Các số dưới đây là **dev V4**, chưa phải confirmation hay toàn LoCoMo. Cùng60 QA được chạy theo ba arrival seed, model Qwen3-4B, GPU KV6GiB, CPU16GiB, FlashInfer/kernel, native LPM16, decode graphs. Gateway giữ nguyên native LPM bên trong. Nguồn: `results/v3/sglang/v4_gateway_dev_analysis.json` và `v4_gateway_dev_quality.json`.

| Policy | Mean p50 TTFT | Mean p95 TTFT | Mean p99 TTFT | Mean answerable F1 |
| --- | ---: | ---: | ---: | ---: |
| Native LPM | 6,149s | 23,062s | 24,694s | 0,3028 |
| FIFO gateway + native LPM | 11,860s | 22,764s | 24,393s | 0,3072 |
| Packing + native LPM | 17,349s | 19,675s | 20,376s | 0,3082 |
| Reuse-gated packing + native LPM | 16,838s | 19,207s | 19,902s | 0,3075 |

**Hỏi: Có thể nói candidate thắng native LPM không?**

Có thể nói nó giảm tail trong điều kiện dev đã đo, nhưng phải nói cùng lúc median tăng rất lớn. Native LPM có thể phục vụ một phần request nhanh, trong khi nhóm khác chờ lâu; packing thay đổi thứ tự và số request được đưa vào engine nên phân bố latency khác. Chưa đủ dữ liệu để quy toàn bộ hiện tượng cho fairness giữa conversation; cần đối chiếu timeline từng nhóm. Nếu sản phẩm coi p50 là mục tiêu chính, đây có thể là một lựa chọn tệ hơn. Research claim cần chỉ rõ mục tiêu tail/fairness, mức giá ở median và miền tải có lợi, rồi xác nhận ngoài dev.

**Hỏi: Tại sao không chỉ so với FIFO gateway?**

Gateway tự có chi phí tokenization, lập lịch, HTTP hop và điều tiết concurrency. Bảng cho thấy riêng FIFO gateway đã tăng median so với native direct. Nếu chỉ so candidate với gateway FIFO, ta có thể bỏ qua baseline native nhanh hơn ở một chỉ số quan trọng. Cần cả native direct, gateway FIFO và candidate trên cùng backend; tiếp tục tune concurrency1/4/16/32 để loại khả năng lợi ích chỉ là giảm concurrency.

**Hỏi: Thay đổi giới hạn bypass cho thấy điều gì?**

Một sweep dev seed101 với native in-batch thresholds1024 cho p95 native20,520s. Bypass0/4/8/16/32 cho35,959/19,169/18,311/19,751/20,348s. Mức0 thực hiện ít uncached prefill nhất nhưng tệ nhất về latency; mức8 tốt nhất về tail trong sweep này nhưng median15,565s vẫn cao hơn native4,800s. Đây là dữ liệu tuning một seed, chưa đủ chọn cấu hình để công bố thắng. Guard quá chặt làm head-of-line blocking và có thể phá locality; quá lỏng làm một nhóm đợi lâu. Audit raw log xác nhận số bypass thực đạt0/4/8/16/19, thay vì suy ra từ tham số cấu hình.

**Hỏi: SGLang đã có kiểm tra memory trước admission, vậy gateway bổ sung gì?**

Trong `PrefillAdder.add_one_req` của phiên bản đã pin, engine kiểm tra phần input còn lại cộng max-new-token và một safety page, rồi kiểm tra lại sau khi lock cache node. Vì vậy không được nói engine bỏ quên memory budgeting. Gateway dùng hợp các block prompt của toàn bộ request đang active để điều tiết **những request nào được nhìn thấy bởi engine và vào thời điểm nào**; nó không sở hữu allocator và không bảo đảm node vẫn resident khi dispatch. Cần ablation với concurrency cap và native scheduler mạnh để chứng minh lợi ích bổ sung.

**Hỏi: Có phải candidate bắt engine restore thay cho recompute không?**

Không. Gateway hiện chỉ điều khiển admission/order. HiRadix có nhánh all-or-nothing trong `load_back`, nhưng standard admission đang gọi `InitLoadBackParams` mà không truyền `mem_quota`, nên mặc định làNone. Không thể nhìn thấy nhánh quota trong source rồi kết luận đó là nguyên nhân của run này. Cần log các lời gọi và kết quả thực, GPU/host prefix tại admission và lượng compute tương ứng. Hook chẩn đoán được tách khỏi benchmark chính; giả thuyết chưa được đo không trở thành kết luận.

**Hỏi: Vì sao có trường hợp candidate promote nhiều CPU token hơn mà tail tốt hơn?**

Ít transfer chưa chắc tốt nếu đổi lại phải tính lại một prefix dài. Trong ba seed dev, reuse-gated packing có trung bình72.278 uncached token, thấp hơn native90.454; đồng thời nó có166.560 host-promotion token trung bình. Counter promotion của native bị thiếu ở một run, nên aggregate native phải đểnull, không tự điền0. Có thể có đánh đổi giữa compute, restore và queueing, nhưng các tổng counter chưa chứng minh causal path của từng request. Số byte và kernel timeline giúp kiểm tra đánh đổi đó; riêng một cache-hit ratio thì không đủ.

## 15. Đo transfer thật: đơn vị, stream và giới hạn kết luận

**Hỏi: Đã đo được byte thật ở LMCache chưa?**

Trong diagnostic riêng bật batch-invariant và event logging, FIFO57 retrieve event có127.628.476.416byte, còn packing10 event có17.477.664.768byte: giảm khoảng86,3%. Tổng retrieve-phase duration11,630→1,617giây; median effective bandwidth khoảng11,03/10,84GB/s. Hai lượt có120/120 request thành công và0/60 output-hash mismatch. Đây là bằng chứng byte/event và correctness trong chế độ diagnostic; latency của nó không thay thế benchmark thường vì batch-invariant thay kernel. Các byte event giữ nguyên semantics LMCache; không đồng nhất một cách mù quáng với số token được engine sử dụng.

**Hỏi: CUDA events trên HiCache đo khác CPU timer thế nào?**

Hook đặt start event trên load stream thực, sau dependency wait của controller, trước layer đầu; đặt end sau layer cuối. Một thread nền dùng `end.query()` rồi mới đọc elapsed, không gọi synchronize toàn GPU. Diagnostic candidate có9 load,166.560token,24.560.271.360byte; coverage token khớp counter promotion. Tổng GPU load-stream span2,175giây, median effective11,29GB/s. CPU enqueue timer chỉ0,120giây cho cùng run, vì đo công đoạn CPU khác. Khoảng GPU này bao gồm cả khoảng hở do CPU chưa enqueue layer kế tiếp; nó không phải tổng thời gian thuần của từng DMA kernel.

**Hỏi: Từ tổng2,175giây có suy ra TTFT giảm đúng2,175giây không?**

Không. Các transfer có thể chồng lên compute, nằm ngoài critical path của một số request, hoặc phải chờ dependency. Tổng thời gian nhiều event cũng không bằng độ dài hợp các interval nếu các event overlap. Muốn nói phần transfer được che bởi compute cần timeline có chung trục GPU, phân loại đúng kernel model và kernel GPU-assisted I/O, rồi lấy giao các interval. CPU timestamp lúc launch cộng CUDA elapsed riêng lẻ chưa đủ dựng timeline GPU chính xác. Hiện chưa có claim overlap steady-state.

**Hỏi: Native không có transfer event thì có được điền counter0 không?**

Chỉ được báo hook quan sát0 lời gọi trong cửa sổ đã instrument. Nếu Prometheus chưa tạo series vì không có observation, giá trị counter nguồn vẫn lànull và coverage với counter chưa xác nhận được. Hai thông tin phải được giữ riêng. Điều này tránh biến thiếu telemetry thành một phép đo âm tính chắc chắn.

**Hỏi: Tại sao phải nâng CPU tier khi chạy toàn bộ1.986 QA?**

Phân tích token của mười conversation cho thấy247.808token prefix dùng chung, làm tròn theo chunk256, tương đương34,03125GiB ở144KiB/token. CPU16GiB của dev không giữ được toàn bộ hotset đó. Cấu hình48GiB được chuẩn bị cho full benchmark và phải áp dụng giống nhau cho baseline/candidate. Phần QA suffix/output riêng còn cần bộ nhớ hoặc bị eviction;34GiB không phải peak toàn hệ thống. Đổi host budget tạo một regime khác: không được gán mọi khác biệt dev/full cho số conversation hoặc scheduler.

**Hỏi: Vì sao không tăng GPU KV cho vừa tất cả?**

GPU24GiB còn phải giữ weight, activations, graph buffers và workspace. Prefix chung của toàn bộ dataset đã khoảng34GiB KV, vượt cả VRAM vật lý trước khi tính weight. Dùng CPU tier là một regime thực sự cần tiering ở cấu hình này. Tuy vậy arrival process là synthetic exponential trên văn bản LoCoMo, không phải log production; cả kết quả tích cực lẫn giới hạn workload phải được ghi rõ.

### 15.1. Một ví dụ duplicate prefill đã quan sát được trên SGLang

**Hỏi: Có ví dụ cụ thể cho thấy cùng prefix vẫn có thể bị tính lặp không?**

Diagnostic HiCache4B V4 seed101 nối được đầy đủ60 request với token của prompt bằng SHA256, rồi ghi các interval prefill được chọn. Tổng interval82.470token khớp chính xác counter uncached của native. Trong batch được dựng lại số4, bốn QA đầu của conv30 đều bắt đầu compute ở vị trí13.280, trong khi context dùng chung kéo dài đến15.188. Như vậy mỗi request tính lại1.908token context giống nhau trong batch đó; tổng7.632token cho phần này, nhiều hơn tính một lần5.724token. Đây là interval theo vị trí token, không phải suy đoán từ chuỗi văn bản giống nhau.

Trên toàn run native, phần context lặp trong **cùng batch** là16.412token. Diagnostic packing_reuse q8 còn9.928token, tổng prefill75.862token cũng khớp counter. Native không gọi load_back trong cửa sổ; candidate có5 lần,98.288token, tất cả thành công và `mem_quota=None`. Những dữ liệu này phân biệt được bớt tính lặp với việc sử dụng thêm CPU restore; không được gộp hai cơ chế thành một cache-hit ratio.

**Hỏi: Vì sao đã có prefix caching mà vẫn xảy ra như vậy?**

Một producer còn đang prefill theo chunk. Prefix từ các chunk trước đã có trong cache; phần cuối của chunk hiện tại chưa thể phục vụ follower trong cùng forward. Nếu engine chọn cả producer và follower cùng tính phần cuối đó, chúng có chung prefix trong tương lai nhưng chưa có KV sẵn dùng tại thời điểm dựng batch. Cần tách “token giống nhau”, “đã tính ở một chunk trước” và “đang được tính trong batch này”. First-token của producer là một proxy muộn hơn cho full-prefill readiness, không phải thời điểm chính xác mọi layer/block đã sẵn sàng.

**Hỏi: Native đã có in-batch prefix caching, sao không mặc định kết luận engine bị lỗi?**

Native có heuristic chỉ kiểm tra in-batch khi prefix GPU hiện có nhỏ hơn một threshold. Threshold32 hoặc1.024 vẫn bỏ qua trường hợp đã có13.280token nhưng còn một suffix dài cần tính. Đây là một giả thuyết có thể kiểm tra: tăng threshold kiểm tra lên32.768, đo lại latency và work, rồi xem tuning native có giải quyết được không. Phần sort/deprioritize cũng chưa chắc là cấm follower vào cùng batch. Không được gọi đây là bug hay đóng góp mới trước khi kiểm tra baseline được tune và chi phí CPU tăng thêm.

**Hỏi: Bằng chứng này có đảo ngược kết luận fixed-DHAS trên vLLM không?**

Không. Đây là engine SGLang, phiên bản/prompt/concurrency cụ thể và diagnostic riêng. Những lượt vLLM trước không thấy fixed200ms DHAS tiết kiệm work vẫn là kết quả âm tính hợp lệ trong phạm vi của chúng. RQ0 phải trả lời theo engine, trạng thái prefix và lịch arrival; không có một kết luận chung rằng mọi prefix follower đều cần delay.

**Hỏi: Làm sao tin phép dựng lại batch?**

Event ở `add_one_req` ghi số request đã chọn trước đó; event ở `add_chunked_req` đánh dấu continuation được thêm trước. Analyzer bắt đầu batch khi số đã chọn là0 hoặc xuất hiện continuation, rồi kiểm tra số đã chọn khớp độ dài batch đang dựng tại từng bước. Mỗi interval được nối với tokenized prompt thật; tổng phải đối chiếu counter. Phép đo này chứng minh công việc prefill được scheduler chọn, không tự cho biết thời gian kernel hoặc số FLOP thực. Muốn khẳng định chi tiết GPU execution cần timeline/kernel instrumentation bổ sung.
