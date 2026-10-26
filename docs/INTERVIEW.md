# CacheFlow: tài liệu phỏng vấn Inference Engineer

**Checkpoint16:36UTC:** diagnostic off/on/off660request hoàn tất, không tái hiện stall gốc; đã đo được2,021GiB cấp phát prefix trùng trong một snapshot bundle restore. V6 readiness+union và baseline chỉ có gate đang ở pilot dev, chưa có kết luận. V5 full benchmark chưa chạy; không gộp số V5/V6.

**Đính chính15:38UTC:** validation57lượt hoàn tất nhưng một main repeat đã được manual abort sau khi mắc kẹt, giữ đủ40kết quả client; full study chưa bắt đầu. Budget cấu hình bằng byte không bảo đảm allocator thật bằng nhau: LMCache lazy làm tròn64MiB, hiện quan sát16.039.018.496byte so native16.000.745.472(+0,2392%). Các so sánh policy trong cùng engine vẫn cùng budget; không dùng mô tả “khớp tuyệt đối dung lượng thật giữa hai stack”. Chi tiết/source hash ở `results/v3/v5_host_allocator_rounding.json`.

**Cập nhật 26/10/2026:** V5 dùng Qwen3-4B, đã audit57lượt validation/2820request không lỗi và đang chạy các lượt lặp protocol đã sửa; full study còn chờ. V4 có lỗi chỉ dẫn abstention mâu thuẫn; các số V4 dưới đây giữ phạm vi lịch sử, không gộp với V5. Phần21 giải thích lỗi, timeout và profiling mới nhất; phần18–20 là các bài học/cấu hình V4. Các phần V2/diagnostic giữ phạm vi lịch sử của chúng; không dùng số của model1.7B để tính ngân sách4B. Chưa có kết luận thắng toàn diện hoặc quality equivalence. Đọc cùng `docs/PROPOSAL_LOCOMO_AGENTPERF_V2.md`, `docs/V3_RESEARCH_PLAN.md` và `docs/V3_BASELINES.md`.

## 1. Kể project trong hai phút

CacheFlow nghiên cứu cách phục vụ nhiều câu hỏi dùng lại các lịch sử hội thoại dài. Thay vì prefill lại toàn bộ lịch sử mỗi lần, engine có thể tái dùng KV cache của prefix giống hệt về token. GPU nhanh nhưng bộ nhớ hạn chế; CPU RAM giữ được nhiều KV hơn nhưng cần chuyển lại qua PCIe. Project đặt câu hỏi: khi nào tier CPU thực sự giúp, khi nào scheduling có thể tránh việc tính/chuyển dữ liệu thừa, và lợi ích đó còn giữ được khi tính toàn bộ thời gian từ lúc request đến hay không?

Stack hiện tại là Qwen3-4B BF16 trên RTX 3090, vLLM làm inference engine, LMCache giữ CPU KV, và gateway Python điều khiển admission. LoCoMo cung cấp hội thoại thật và QA; arrival là workload được xây dựng có công bố seed, không phải trace production. V2 xác nhận cơ chế tiering và bẫy đo counter. V4 bổ sung admission theo hợp bộ nhớ prefix, đối chiếu vLLM/LMCache và SGLang/HiCache đã tune. V5 giữ phương pháp đó, sửa mâu thuẫn chỉ dẫn trong prompt và mở rộng timeout đo lường; full benchmark và audit cuối vẫn chưa hoàn tất.

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

Với full attention, xấp xỉ `bytes/token = 2 × layers × KV_heads × head_dim × bytes/element`. Hai lần là K và V. Model4B hiện dùng có36 layer,8 KV head, head dimension128 và BF16 hai byte: `2 ×36 ×8 ×128 ×2 =147.456 byte/token`, tức144KiB/token. Một context32.768token cần4,5GiB KV, chưa tính weights, allocator, activation, runtime và fragmentation. Model1.7B lịch sử có28 layer, tương ứng112KiB/token và3,5GiB cho32K; đó là một geometry khác.

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

Các phần10–17 giải thích diagnostic và các quyết định phát triển. Phần18 sửa đơn vị ngân sách; phần19 trình bày dev/held-out, tradeoff chất lượng và phân rã latency; phần20 diễn tập tính bộ nhớ/admission. Full benchmark chưa hoàn tất nên các kết luận full vẫn để mở.

## 10. Profiling V3 đã quan sát: bài học có số liệu

Các số dưới đây là diagnostic/screen, chưa phải kết luận contribution cuối.

**Câu hỏi: Bạn từng gặp profiler làm sai kết luận chưa?**

Có. Cùng trace dev 60 QA và cùng cap 16, run bật PyTorch profiler có p95 khoảng 31.03 giây; run unprofiled khoảng 3.57 giây. Nếu xem run có profiler là baseline thật, ta sẽ tưởng queueing là vấn đề lớn hơn thực tế rất nhiều. Profile CUDA window thu được khoảng 8.32 giây, model-kernel union khoảng 6.43 giây; phần này chủ yếu là đầu trace/cold phase. Vì vậy không dùng nó đại diện toàn bộ steady state. Trace được giữ để xem kernel/dependency; latency chính phải lấy từ unprofiled comparisons.

**Câu hỏi: Bạn kiểm tra bandwidth đường CPU–GPU thế nào trước khi tối ưu?**

`nvidia-smi` báo link tối đa thực tế trên host này là Gen3 x16, dù tên card có thể khiến mình nghĩ tới Gen4. Từ encoding PCIe Gen3, băng thông lý thuyết một chiều x16 xấp xỉ 15.75 GB/s, trước protocol overhead. Lightweight LMCache GPU-stream events ghi 56 retrieve events, khoảng 121.7 GB payload, 10.73 giây duration cộng dồn; median event throughput khoảng 11.35 GB/s. Đây là băng thông transfer, không phải throughput request và không phải toàn bộ latency request. Tổng thời gian event có thể overlap, nên không cộng thẳng vào E2E TTFT.

**Câu hỏi: Tại sao không kết luận cần viết kernel H2D nhanh hơn ngay?**

Băng thông đã đạt phần đáng kể giới hạn link; cải thiện kernel có trần lợi ích. Giảm byte phải chuyển bằng residency/locality có thể có headroom lớn hơn, nhưng có nguy cơ tăng queue wait hoặc starvation. Screen cho thấy có policy giảm transfer mà p95 vẫn xấu hơn. Cần tối ưu outcome cuối, không chỉ một resource counter.

**Câu hỏi: Model lớn hơn làm capacity planning thay đổi gì?**

Model 4B hiện dùng có 36 layer thay vì 28. Với 8 KV head, head dimension 128 và BF16, KV là 144 KiB/token; context 32K cần 4.5 GiB KV. Vì vậy không được bê nguyên budget 4 GiB từ model 1.7B rồi gọi OOM là method failure. Model và checkpoint phải được pin/verify trước khi dùng; đoạn này ban đầu được viết trước khi tải xong, còn hiện tại cả ba shard đã được kiểm SHA và các lượt GPU dev/held-out đang được đánh giá.

**Câu hỏi: Một baseline cache-aware mạnh có thể vẫn làm hại fairness như thế nào?**

LPM có thể ưu tiên request khớp prefix vừa dùng, giảm migration từ CPU nhưng làm nhóm khác đợi. Cap 1 có thể giúp locality song làm mất batching. Bundle theo wave giúp một số shared-prefix requests nhưng có thể phải đợi request sinh dài nhất trong wave. Cần cùng cap, cùng engine và cùng trace để phân biệt lợi ích ordering với lợi ích throttle; kiểm tra p95/p99 và từng nhóm request, không chỉ median.

### 10.4. Vì sao “request gần nhất” không đồng nghĩa với KV đang ở GPU?

**Hỏi:** Dùng conversation vừa phục vụ để chọn request tiếp theo có đủ chính xác không?

**Đáp:** Không. Trong thời gian một request decode, những request khác có thể làm các block cũ bị thu hồi. Một conversation cũng có thể chỉ còn một phần prefix trên GPU. LPM-hint của baseline dùng lịch sử request nên chỉ là tín hiệu gần đúng. Baseline actual-GPU LPM và prototype residency V3 đã dùng sự kiện `BlockStored`, `BlockRemoved`, `AllBlocksCleared` mà vLLM phát ra. Gateway tạo cùng chuỗi hash theo block 16 token và đếm prefix liên tiếp còn trong index. Thông tin này vẫn có độ trễ truyền sự kiện; nó là ước lượng phục vụ admission, không phải quyền sở hữu hay khóa block trong allocator.

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

**Đáp:** Lấy hợp các hash block đầy đủ của các request đang active, mỗi hash chỉ tính một lần. Sau đó cộng riêng đuôi prompt chưa đủ block, ngân sách token sinh và một block dự phòng cho từng request, làm tròn theo block. Đây là dự phòng bảo thủ ở cấp gateway; allocator thật còn có null block, copy-on-write và thời điểm giải phóng bất đồng bộ. Prototype1.7B lịch sử dùng37.424token thay vì37.440 để chừa null block. Cấu hình4B/GPU6GiB hiện dùng43.664token admission so với43.680token pool vật lý. Engine vẫn chịu trách nhiệm bảo vệ bộ nhớ và tính đúng của attention.

**Hỏi:** Khi request đầu hàng không vừa thì phải làm gì?

**Đáp:** Có thể cho một request phía sau dùng chung prefix với nhóm đang active đi trước, nếu dự phòng bộ nhớ vẫn vừa. Nhưng phải giới hạn số lần vượt hàng. Prototype lịch sử cho phép bốn lượt; cấu hình V4 đã khóa cho phép tám lượt, rồi ngừng backfill để các request đang chạy hoàn thành và request cũ được phục vụ. Khi không có active request, luôn cho request cũ nhất tiến lên; nếu chỉ chờ một ước lượng vừa bộ nhớ, một request dài đơn lẻ có thể bị kẹt vô hạn.

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

Đã chạy upstream SGLang0.5.14 với HiCache/LPM trên cùng model 1.7B, prompt V3 và dev trace 60 QA. Một run hợp lệ đã kiểm tra token prompt, capture output và native metrics; p95 khoảng 6,94 giây ở seed101. Cấu hình có decode CUDA graphs, cache GPU37.440 token và CPU16 GB thập phân (đơn vị native HiCache). Đây là kết quả dev ban đầu, còn cần thêm seed và tune backend. Không gọi nó là toàn bộ Strata: việc dùng HiCache không tự động tái hiện mọi thành phần scheduler trong paper.

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

## 14. Ma trận HiCache ban đầu và cách giải thích tradeoff

Các số dưới đây là **dev V4 giai đoạn đầu, trước guard**, chưa phải cấu hình cuối hoặc confirmation/toàn LoCoMo. Kết quả cấu hình guard/Direct mới hơn ở phần19. Cùng60 QA được chạy theo ba arrival seed, model Qwen3-4B, GPU KV6GiB, CPU16GB thập phân, FlashInfer/kernel, native LPM16, decode graphs. Gateway giữ nguyên native LPM bên trong. Nguồn: `results/v3/sglang/v4_gateway_dev_analysis.json` và `v4_gateway_dev_quality.json`.

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

Phân tích token của mười conversation cho thấy247.808token prefix dùng chung, làm tròn theo chunk256, tương đương34,03125GiB ở144KiB/token. CPU native16GB của dev không giữ được toàn bộ hotset đó. Cấu hình native48GB (payload sau làm tròn48.002.236.416byte, khoảng44,706GiB) được chuẩn bị cho full benchmark và phải áp dụng giống nhau cho baseline/candidate. Phần QA suffix/output riêng còn cần bộ nhớ hoặc bị eviction;34GiB không phải peak toàn hệ thống. Đổi host budget tạo một regime khác: không được gán mọi khác biệt dev/full cho số conversation hoặc scheduler.

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

### 15.2. Vì sao xóa KV cache chưa đủ để reset một thí nghiệm scheduler?

**Hỏi: Đã gọi flush_cache rồi, vì sao một run vẫn có thể bị nhiễm trạng thái?**

KV cache của engine và lịch sử của gateway là hai nơi khác nhau. Gateway giữ một deque các request đã hoàn thành để nhận diện prefix từng xuất hiện. Nếu xóa GPU/CPU KV nhưng không xóa deque, một policy reuse-gated có thể bật packing ngay ở lượt sau dù lượt trước bắt đầu với lịch sử rỗng. Không có gold-answer leakage, nhưng trạng thái ban đầu giữa các run đã không còn giống nhau.

**Hỏi: Project đã gặp lỗi này thật chưa và xử lý ra sao?**

Có. Script control mới tái dùng gateway qua nhiều run, trong khi script ma trận Direct/kernel chính restart gateway từng arm. Năm candidate control được phát hiện có decision counter khác0 ngay trước replay và bị đánh dấu invalid. Toàn bộ raw output được giữ; các bảng cap4 cũ có thông báo invalidation, không còn được dùng để nói đã lặp thành công ba seed cho candidate đó. Native direct không tiêu thụ state gateway nên vẫn là phép đo native hợp lệ. Control bị ảnh hưởng cần chạy lại với ID mới.

**Hỏi: Cổng kiểm tra mới chứng minh được gì?**

Benchmark restart gateway khi nó idle, chờ ready, rồi yêu cầu cả số completed-history request và decision calls bằng0. Sau đó mới capture setup/replay với cache engine được reset. Đây là bằng chứng mạnh hơn chỉ nhìn active=queue=0: một scheduler đang rảnh vẫn có thể nhớ nhiều prefix. Kiểm tra này không thay thế audit model/config/token/output hoặc tránh được mọi dạng state khác; mỗi thành phần có cache/lịch sử đều cần một reset contract rõ ràng.

## 16. Tách CPU preparation khỏi event loop: đo gì và không suy ra gì?

**Hỏi: Ngoài scheduler, gateway còn giữ event loop ở đâu?**

Log của các run HiCache4B cho thấy tokenization khoảng68ms và prefix hashing khoảng12ms mỗi request. Đây là CPU work chạy đồng bộ ngay trong async HTTP handler. Trong thời gian đó, event loop cũng không relay token, đọc socket hoặc giải phóng ticket. Tên hàm là `async` không tự làm CPU work bên trong trở thành bất đồng bộ.

**Hỏi: Vì sao chọn một worker riêng thay vì cho32 thread encode đồng thời?**

Tokenizer có cấu hình mutable như truncation/padding. Nhiều thread dùng chung có thể đụng trạng thái đó. Một `ThreadPoolExecutor(max_workers=1)` tuần tự hóa preparation, kể cả khi HTTP task bị cancel mà CPU job chưa dừng. CPU worker tạo token IDs và cả hai loại hash; event loop nhận kết quả rồi mới admission. Cả baseline và candidate đều được bật/tắt cùng chế độ trong phép so phù hợp; không được cấp tối ưu này riêng cho candidate.

**Hỏi: Đã kiểm chứng tương đương và responsiveness ra sao?**

CPU-only microprofile chạy20 prompt dev thật ở trạng thái preparation liên tục, với heartbeat1ms. Hai chế độ trả đúng token IDs, prefix hash256 và engine hash16 giống nhau, đồng thời khớp tokenizer counts của trace. Inline mất1,025giây, worker1,135giây; heartbeat gap lớn nhất giảm161,59→12,86ms, p99 161,04→10,97ms. Bài đo này không dùng GPU và không phải speedup end-to-end; nó chứng minh luồng CPU có thể chậm hơn một chút mà event loop vẫn đáp ứng tốt hơn. Nguồn: `results/v3/prepare_eventloop_profile.json`.

**Hỏi: Đưa sang thread có loại hết tác động của GIL không?**

Không. Rust tokenizer có thể nhả GIL, nhưng hashing và bookkeeping Python vẫn tranh GIL với event loop. Thread cũng có scheduling overhead. Vì vậy heartbeat vẫn có gap hàng chục ms, không có hard latency bound. Cần đo GPU run sau thay đổi để xem stream progress, queue và prefill batching có tốt hơn không; không lấy tỷ số heartbeat làm tỷ số TTFT.

**Hỏi: Thời gian chờ trong executor có bị giấu đi không?**

Không. Client arrival-TTFT vẫn bắt đầu từ scheduled arrival, trước cả HTTP preparation. Gateway ghi riêng `prepare_queue_ms` và `prepare_cpu_ms`; `ingress_prepare_ms` bao gồm preparation và thời gian chờ worker trước admission. Nếu worker quá tải thì số đó và backlog tăng, và kết quả phải thể hiện điều này. Offload chỉ đổi nơi thực thi CPU work, không xóa công việc hoặc thời gian chờ.

**Hỏi: Vì sao còn phải thử cap64 khi engine vẫn chỉ chạy16 request?**

Cap ở gateway quyết định engine được nhìn thấy bao nhiêu request đang chờ; max-running của engine quyết định bao nhiêu request được thực thi. Một FIFO gateway cap16 có thể che đi các request mà native LPM muốn chọn, ngay cả khi cả working set đã vừa GPU. Control GPU-fit của cap16 ghi p95 tăng2,14/5,24/6,48% và median tăng lớn, dù không có host-promotion series. Cần so native direct, FIFO64 và union-admission64 trên cùng engine16 để tách visibility/concurrency khỏi memory policy. Đây là động cơ của phép kiểm tra cap64. Validation mới ở phần19 cho thấy GPU-fit cap64 chỉ tăng p95 khoảng0,48–1,19% trong ba seed; không được biến kết quả này thành bảo đảm cho mọi cache size hoặc mức tải.

## 17. Biến một cơ chế paper thành baseline có thể kiểm tra

**Hỏi: Native in-batch threshold lớn có tái hiện delay-hit deferral trong Strata không?**

Chưa. Kiểm tra prefix và giảm priority không đồng nghĩa cấm follower vào batch đang tính producer. Pilot threshold32K vẫn compute78.662token ở cap16, p95 khoảng20,82s. Component thử nghiệm tiếp theo nhìn vào các request đã được chọn trong batch: nếu follower còn thiếu hơn100token prefix mà producer đang tính, nó tạm chưa được thêm vào batch. Đây là adaptation của một thành phần trong Strata4.3.1, không phải toàn bộ hệ thống paper.

**Hỏi: Guard có đọc KV từ GPU hoặc sửa allocator không?**

Không. Nó đọc độ dài prefix/chunk từ metadata CPU và so sánh exact token arrays của toàn bộ prefix đến interval cần kiểm tra. Host-hit tokens được tính là đã cache để tránh nhầm restore bundle với duplicated compute. `extra_key` phải giống nhau; hybrid/Mamba requests được bỏ qua vì có lifecycle tài nguyên riêng. Native vẫn lookup, lock, allocate, load và execute KV. Không tạo shared KV chỉ vì hai đoạn văn bản giống nhau ở giữa prompt.

**Hỏi: Tại sao trả CONTINUE mà không thêm follower vào can_run_list?**

Trong scheduler phiên bản đã pin, CONTINUE tiếp tục xét request khác; sau batch, engine chỉ xóa khỏi waiting queue các request có trong can_run_list. Follower bị defer vì vậy còn ở queue cho round sau. Trả OTHER sẽ kết thúc scan ngay, có thể bỏ lỡ complementary work. Guard chỉ defer khi đã có producer được chọn, nên bản thân nó không tạo batch rỗng với tất cả request tự chờ nhau. Điều này không hứa hẹn một hard wall-time fairness bound.

**Hỏi: Pilot guard đã chứng minh điều gì?**

Trên dev seed101, ba arm đo chính thức đều60/60 thành công. Native guard p95=17,262s; thêm FIFO64 gateway18,083s; thêm packing64-worker16,049s. Packing giảm p99 khoảng10,66% so với native guard nhưng median tăng4,294→13,490s. Cả ba compute69.590 uncached token, trong khi promotions26.448/0/90.144 khác nhau. Vì thế không được giải thích tail gain này bằng “candidate tính ít token hơn” hoặc “luôn giảm transfer”. Một seed cũng chưa chứng minh được tính lặp lại. Cần xem per-conversation latency, actual bypass, migration và chạy workload lớn trước khi chốt claim.

**Hỏi: Vì sao không gọi baseline này là Strata rồi công bố thắng paper?**

Paper còn có transient nodes xuyên qua in-queue/in-flight, balanced-batch formation và bubble filling. Guard ở đây chỉ xử lý trùng compute giữa các request được chọn trong cùng batch, dùng Python và giữ native LPM. Hiệu năng trên RTX3090/LoCoMo của component adaptation không đồng nghĩa hiệu năng hệ thống Strata đầy đủ. Tên baseline, component scope, source/env hashes và những phần chưa tái hiện đều phải công khai.


## 18. GB, GiB và một phép so sánh có thể sai từ cấu hình

**Hỏi: Hai engine đều ghi CPU cache16, tại sao chưa chắc cùng ngân sách?**

**Đáp:** HiCache chuyển16 thành16 tỷ byte, chia cho byte/token rồi làm tròn lên một page16token. LMCache nhận16 theoGiB, tức16×2^30byte. Với Qwen3-4B144KiB/token, pool native16GB thực là16.000.745.472byte; flag LMCache khớp là14,90185546875GiB. Chênh lệch đơn vị khoảng7% có thể đổi eviction, hit rate và latency. Bởi vậy phải kiểm mã nguồn parser và argv thực tế, không chỉ tên flag trong script.

Các phép so baseline/candidate trong từng engine dev dùng cùng ngân sách nên vẫn có giá trị. Tuy nhiên không được gọi ngân sách CPU của hai engine dev lịch sử là bằng nhau. Trước held-out, revision1 đã sửa cấu hình bằng byte; thuật toán/cap/bypass giữ nguyên. Full dùng48.002.236.416byte ở cả hai stack. Seal revision0 và trace CPU cũ được giữ lại để audit; chúng chưa được chạy GPU.

**Hỏi: Vì sao không sửa trực tiếp cấu hình sau khi nhìn held-out?**

**Đáp:** Khi đã dùng kết quả để chọn phương pháp, tập đó trở thành dev. Chúng tôi khóa source, prompt, ngân sách, cap64 và bypass8 bằng SHA trước lần chạy GPU đầu của conv43/44. Nếu kết quả xấu, phải báo kết quả xấu; một phương pháp sửa tiếp cần protocol và tập xác nhận mới.

## 19. Kết quả tốt phải đi kèm điều kiện áp dụng

**Hỏi: Số liệu dev mạnh nhất hiện tại là gì?**

**Đáp:** Trên vLLM/LMCache,18 lượt đo gồm6 policy×3 arrival seed,60 QA duy nhất, tất cả1080 request thành công. P95 trung bình FIFO64/bundle16/union64 lần lượt36,679/27,948/19,615giây. Union p50=15,463giây so với FIFO64=25,472giây. CPU KV engine thực sự tiêu thụ giảm từ khoảng918.373 xuống75.349token/run. Đây là token-source accounting; chưa được đổi trực tiếp thành byte DMA vì engine có thể đọc thêm chunk hoặc dùng đường truyền khác.

Trên SGLang/HiCache Direct đã bật cùng guard cho mọi arm,33 lượt validation/1668request thành công. P95 union so với nativeLPM giảm11,27–20,62% theo seed; nativeDFS cũng có tail kém hơn union trong dev này. Nhưng median tăng đáng kể: policy có thể trì hoãn nhóm nhanh để nhóm bị pressure được tiến lên. Low-reuse chỉ tăng p95 tối đa khoảng0,23%, GPU-fit khoảng1,19%; ở2QPS có seed tăng p95 tới11,87%. Tôi sẽ trình bày cả các điểm này thay vì nói scheduler luôn thắng.

**Hỏi: Ba seed có nghĩa là180 câu hỏi độc lập?**

**Đáp:** Không. Vẫn60 câu hỏi, chỉ đổi lịch đến và thứ tự chạy policy. Phải giữ paired contrast theo seed và conversation. Ba lần thắng giúp đánh giá độ ổn định serving, không tạo thêm độ đa dạng ngữ nghĩa. Held-out40QA và full1986QA vẫn cần được báo riêng; full còn chứa lại dev/held-out nên không phải1986 câu xác nhận độc lập.

**Hỏi: CUDA trace ít memcpy có chứng minh ít PCIe traffic không?**

**Đáp:** Chưa. Trong diagnostic CPU-hot Direct, counter ghi238.400token được promote, tương ứng35.153.510.400byte KV payload cho mỗi phase12request. Nhưng trace GPU-only không thể hiện đầy đủ bulk transfer dưới dạng event memcpy thông thường. Direct có đường batched-copy; công cụ có thể thiếu coverage API đó. Cần đối chiếu CUDA-event hook và counter trước khi tính overlap. Không được lấy thời gian launch trên CPU cộng duration CUDA rồi gán thành một khoảng GPU tuyệt đối: chúng thuộc hai clock khác nhau.

**Hỏi: Làm sao biết profiler không phá kết quả?**

**Đáp:** Chạy off/on/off cùng prompt và trạng thái CPU-hot, tắt stack/shape, chỉ thu hoạt động GPU. P95 khoảng492/492/493ms, cùng238.400token promote và254token compute mỗi phase. Chênh lệch nhỏ cho thấy overhead thấp trong diagnostic này; không chứng minh profiler hoàn toàn không ảnh hưởng mọi workload. Các lượt này chỉ sinh4token để soi đường truyền, tách khỏi QA cap96 và bảng latency chính.

### 19.1. Held-out đã làm thay đổi kết luận như thế nào?

Ngày26/10/2026, toàn bộ27 lượt xác nhận trên conv43/44 hoàn tất1080/1080request,40QA duy nhất lặp ba lịch đến. Source/config đã khóa trước GPU evaluation; không thay phương pháp sau khi nhìn kết quả. Trên vLLM, union giảm p95 khoảng40,3–43,9% so vớiFIFO64 và25,0–29,7% so vớibundle16. Tuy vậy F1 so vớiFIFO giảm khoảng0,0046–0,0104; so vớibundle có seed tăng, có seed giảm. Không được chỉ nói “latency thắng và quality giữ nguyên”.

Trên SGLang Direct+guard, p95 giảm3,9–8,7% so với nativeLPM ở4QPS và3,8–8,6% so với nativeDFS. Median tăng khoảng41–46% so vớiLPM; F1 giảm0,0034–0,0203 theo cặp. Gain held-out nhỏ hơn dev: đây là bằng chứng phải giảm độ mạnh của claim và xem full quality/category, không phải lý do đổi seed hay retune. Ở2QPS held-out tail lại tốt hơn8,3–14,8%, nhưng không xóa seed dev2QPS bị regression11,9%; hai tập có geometry và thứ tự arrival khác nhau.

**Hỏi: Nếu người phỏng vấn hỏi có thể đưa vào production chưa?**

**Đáp:** Tôi chưa có bằng chứng đủ để bật rộng rãi. Có lợi ích rõ trong một số regime pressure và stack, nhưng tradeoff median và sai khác chất lượng vẫn phải audit. Cần thêm full-data evaluation, SLO theo nhóm và kiểm tra numerical batching. Trong production, policy cần được đánh giá bằng arrival-based latency và chất lượng của cùng output, chứ không chỉ giảm engine queue. Bypass8 chỉ giới hạn số lần vượt đầu hàng trước handoff, không cam kết deadline hay công bằng E2E của native engine.

### 19.2. Làm sao chứng minh không chỉ chuyển queue ra gateway?

Tôi dựng lại từng request từ cùng clock monotonic trên host, rồi kiểm tra tổng các khoảng khớp arrival-TTFT. Với held-out seed701 trên vLLM, FIFO có mean28,16giây; union17,95giây. Union chờ admission13,84giây nhưng phần handoff→token chỉ4,00giây, còn FIFO gần như không chờ gateway nhưng handoff→token28,05giây. Tổng giảm khoảng10,21giây: lợi ích không chỉ là đổi chỗ ghi queue.

Cùng seed trên SGLang, FIFO mean10,97giây còn union15,45giây. Union làm p95 tốt hơn nhưng mean xấu hơn khoảng4,48giây. Vì vậy người review phải thấy cả mean/median/tail, và SLO quyết định tradeoff có hữu ích hay không. Tôi không gọi phần handoff→token là GPU compute: nó còn gồm native queue, KV load và transport. P95 của từng stage cũng không cộng thành p95 tổng vì các request chậm nhất ở mỗi stage có thể khác nhau.

## 20. Diễn tập thiết kế: từ công thức bộ nhớ đến quyết định admission

**Hỏi: Vì sao tám request có thể nhẹ bộ nhớ hơn hai request?**

**Đáp:** Giả sử tám request cùng một causal prefix gồm30.000token đầy block16, và tạm bỏ qua mọi prompt tail. Mỗi request dành96token output cùng16token an toàn. Hợp prefix vẫn chỉ30.000token; phần riêng là8×112=896token. Tổng dự phòng30.896token, nằm trong ngân sách admission43.664token của GPU KV6GiB. Với144KiB/token, phần prefix chung chiếm khoảng4,12GiB; mỗi tail112token tương ứng15,75MiB. Đếm request rồi nhân nguyên prompt tám lần sẽ đánh giá quá cao.

Ngược lại, hai prefix hoàn toàn khác nhau dài28.000 và22.000token cần50.000token trước khi cộng tail/output; không vừa43.664token. Đây là ví dụ lý tưởng hóa để thấy vì sao concurrency cap không thay thế token budget. Trong dữ liệu thật phải tính cả phần header chung, tail chưa đủ block và allocator semantics.

**Hỏi: Khi request đầu hàng không vừa mà request phía sau vừa, làm gì?**

**Đáp:** Policy xét request cũ nhất trước. Khi còn active work và có reuse opportunity, nó có thể chọn request phía sau vừa với hợp bộ nhớ hiện tại. Mỗi lần như vậy tăng bypass của đầu hàng; đạt8 lần thì không tiếp tục vượt đầu đó. Active work được phép hoàn tất rồi đầu hàng tiến lên. Khi không còn active request, luôn cho đầu hàng chạy để tránh deadlock vì dự phòng bảo thủ. Đây là giới hạn số quyết định backfill, không phải lời hứa request được phục vụ trong8ms hay8batch native.

**Hỏi: Hợp các hash bằng nhau có bảo đảm chỉ có một bản KV vật lý không?**

**Đáp:** Không. Hash mô tả causal content trong namespace đã kiểm chứng. Engine vẫn có thể giữ bản sao, block đang ghi, copy-on-write hoặc cấp phát ở thời điểm khác. Admission là mô hình dự phòng để sắp thứ tự, không can thiệp allocator hay thay validation KV. Engine chịu trách nhiệm correctness và bảo vệ bộ nhớ. Cần đo preemption, compute, transfer và output thật để kiểm tra mô hình có hữu ích.

**Hỏi: Vì sao hash của riêng một chunk giống nhau chưa đủ?**

**Đáp:** KV của một token trong causal attention phụ thuộc cả prefix trước nó. Hai chunk cùng chữ nhưng đứng sau hai lịch sử khác nhau thường có KV khác. Vì vậy fingerprint phải nối theo causal prefix và namespace phù hợp, gồm các biến ảnh hưởng KV như model/token IDs hay extra key mà backend dùng. Project từng gặp external hash integer64 của vLLM không khớp bytesSHA256 của gateway; event đến đầy đủ vẫn cho mọi lookup miss. Chúng tôi kiểm một payload store thật thay vì chỉ kiểm tên hàm hash.

**Hỏi: Vì sao không đơn giản chọn request hit CPU nhiều nhất?**

**Đáp:** Cache hit cho biết cơ hội reuse, chưa cho biết KV nằm trên GPU hay CPU, copy có bị lặp giữa nhiều request hay không, và request cũ sẽ chờ bao lâu. Một prefix CPU dài có thể gây nhiều I/O hơn một prefix GPU ngắn. Policy union hiện không có oracle CPU residency hoặc quyền ép restore/recompute. Baseline nativeLPM nhìn cả host/device match, nativeDFS nhóm theo cây; phải so với chúng và kiểm tra counter nguồn, không xem mọi token cached như một đơn vị chi phí giống nhau.

**Hỏi: Tại sao cần DFS khi đã có native LPM?**

**Đáp:** Trong SGLang0.5.14 đã pin, LPM chuyển tạm sangFCFS khi waiting queue dài hơn128 để tránh chi phí match/sort. Full run đầu đã quan sát queue255 ở nhiều sample. DFS không dùng điều kiện fallback LPM đó, nên là đối chứng bổ sung quan trọng khi tải lớn. Gauge1Hz chỉ cho biết trạng thái tại các mẫu, không phải log chính xác mọi lần scheduler quyết định. Tôi không gọi thời gian queue>128 là thời gian đã chứng minh engine chạyFCFS ở từng microsecond.

**Hỏi: Giảm engine queue có chứng minh giảm latency không?**

**Đáp:** Không. Chờ có thể chuyển sang connection pool của client, CPU worker hoặc gateway admission. Arrival-TTFT bắt đầu từ lịch đến dự kiến và kết thúc ở token mà client nhận, nên giữ các khoảng đó trong phép đo. Khi hệ thống quá tải, timeout và reject cũng phải báo cùng tổng request; không được bỏ lỗi rồi lấy p95 của những request còn thành công. Full-study audit chỉ chấp nhận các lượt hoàn chỉnh cho bảng latency chính; các lượt thất bại vẫn là bằng chứng về giới hạn vận hành.

**Hỏi: Hai engine khớp48.002.236.416byte CPU cache có đồng nghĩa dùng cùng tổng RAM không?**

**Đáp:** Không. Đây là cùng ngân sách KV payload. Metadata, index, staging buffer, tokenizer, weights trong lúc load và cách reserve/touch page vẫn có thể khác. Tổng RSS của nhiều process còn đếm lặp shared pages, nên không phải số RAM vật lý độc lập đã dùng. Cần giữ capacity cấu hình, actual payload, RSS và RAM khả dụng thành các phép đo khác nhau. So policy trong cùng stack giúp kiểm soát phần lớn những khác biệt implementation này.

**Hỏi: GPU utilization86% có nghĩa là86% thời gian đang làm GEMM không?**

**Đáp:** Không. Đó là quan sát utilization tổng từ công cụ GPU, lấy mẫu theo giây. Attention, memory kernels và GPU-assisted I/O cũng có thể làm GPU bận; các burst ngắn còn bị trung bình hóa. Muốn nói thời gian GEMM/attention hay overlap với transfer phải phân loại event kernel trên cùng timeline. Với timestamp lấy mẫu không đều, phải tính trung bình có trọng số thời gian thay vì trung bình số dòng. Đoạn lấy mẫu đang chạy cũng chưa cho biết p95 của toàn benchmark.

**Hỏi: Vì sao giá trị cuối counter lớn hơn0 nhưng delta vẫn đểnull?**

**Đáp:** Nếu series không có ở đầu cửa sổ, không thể chỉ từ hai endpoint chứng minh baseline bằng0. Analyzer giữ giá trị đầu/cuối, đồng thời để delta nghiêm ngặt lànull. Nếu mã nguồn chứng minh exporter tạo series lười khi lần đầu observe/inc, có thể bổ sung diễn giải có điều kiện, nhưng phải ghi rõ giả định. Trong full native run đầu, `load_back_tokens_total` có giá trị cuối nhưng không có series ở mẫu đầu; công cụ theo dõi giữ cả hai thông tin. Một gauge cũng không được trừ như counter: `num_retracted_reqs` là gauge, còn `num_retracted_requests_total` mới là counter tương ứng trong phiên bản đã pin.

### 20.1. Full baseline đầu tiên:99% cached vẫn có thể rất chậm

NativeLPM/HiCache đầu tiên đã chạy đủ1.986QA, không lỗi. Trace phát request trong510,151giây, nhưng hệ thống mất1.471,821giây để hoàn tất. Arrival-TTFT p50/p95 là494,661/1.059,893giây. Đây là một baseline đang bị backlog ở4QPS, chưa phải kết quả so với candidate; pipeline còn phải chạyFIFO64, union vàDFS theo protocol đã khóa.

**Hỏi: Cache hit hơn99% thì tại sao TTFT vẫn rất cao?**

**Đáp:**50.211.040 trong50.520.339prompt token được native báo cached, nhưng “cached” không có nghĩa mọi KV đang ở GPU và dùng được miễn phí. CPU-backed KV có thể phải nạp lại quaPCIe; queue và decode cũng giữ tài nguyên. Hơn94% cửa sổ lấy mẫu có queue trên128, là điều kiện khiến LPM bản đang pin chuyển sangFCFS. Cần đo thêm nguồn token và đối chứngDFS/FIFO64 trước khi nói cơ chế nào gây từng phần latency. Counter hit cao một mình không chứng minh hệ thống nhanh.

**Hỏi: Full QA có tốt không?**

**Đáp:**Baseline này có F1 khoảng0,320 trên1.540câu có đáp án, nhưng điểm category5 chỉ0,009 trên446câu adversarial. Có23output chạm cap96. Đây là kết quả text-only, budgeted generation theo evaluator gốc; không phải chất lượng leaderboard hay bảo đảm abstention. Cần báo riêng category5 và so output thay đổi theo từng policy. Một bảng serving latency xanh không làm hạn chế hallucination biến mất.

**Hỏi: P95 hơn1.000giây mà không lỗi, có mâu thuẫn với timeout600giây không?**

**Đáp:**Không thể xem một timeout ở client như deadline E2E của mọi request. Arrival-TTFT cộng cả chờ từ lịch đến, transport/pool, native queue và execution. Timeout được áp dụng ở các công đoạn cụ thể, với phạm vi khác tổng thời gian đó. Bằng chứng của lượt này là toàn bộ1.986request thành công, không phải suy luận từ tên cấu hình. Nếu cần SLO tổng600giây, phải định nghĩa và đo deadline từ scheduled arrival một cách tường minh.

## 21. Tự phản biện: phát hiện một sửa lỗi chưa đủ triệt để

**Hỏi: Điểm abstention rất thấp có hoàn toàn do model không biết từ chối không?**

**Đáp:** Chưa thể kết luận như vậy. Khi kiểm tra V4 full prompt, tôi phát hiện system yêu cầu `No information available.` nhưng footer user vẫn yêu cầu `I don't know`. Tôi đã sửa system trước đó nhưng bỏ sót renderer phía trong. Cả1.986prompt đều có mâu thuẫn này. Trong446câu category5 của native full,155output đúng nguyên văn câu trả lời legacy,165output chứa nó, còn evaluator chỉ nhận4output theo hai phrase mà nó quy định.

Điểm official0,009 vẫn là số đúng cho output V4 theo evaluator đã pin; cách diễn giải “model hầu như không abstain” thì quá mạnh. Các con số phrase ở trên chỉ là diagnostic về format, không phải thang đo semantic mới. Tôi giữ nguyên output/score cũ, sửa cả system và user trong versionV5, rồi đo lại mọi arm. Không thay `I don't know` thành phrase được chấm điểm trong output sau khi model đã trả lời.

**Hỏi: Sửa prompt có lén làm thay đổi nội dung hội thoại không?**

**Đáp:** Renderer chỉ bỏ đúng footer cấu trúc ở cuối canonical context và thêm footer nhất quán. Nếu hội thoại hoặc câu hỏi có trích dẫn cùng chuỗi chữ, nội dung đó được giữ nguyên. Test còn thay gold answer, category và evidence trong object rồi kiểm prompt không đổi. Toàn bộ1.986QA vẫn fit, tăng đúng1token; cần tokenize và kiểm lại token với server thay vì mặc định thay vài chữ là miễn phí.

**Hỏi: Nếu tập xác nhận đã được xem rồi, V5 có thể gọi nó là held-out mới không?**

**Đáp:** Không. Conv43/44 đã được chạy dướiV4. V5 là lặp kiểm chứng protocol sửa, không tạo ra tập semantic chưa từng thấy. Thuật toán admission/cap/bypass đã khóa trước V4 exposure và giữ nguyên; bản sửa phrase áp dụng toàn cục, không dùng gold hay evidence từng câu. Tôi công bố cả lịch sử exposure và các version, không gộp bảng V4/V5 để tạo một claim mạnh hơn dữ liệu.

**Hỏi: Tại sao phải sửa timeout bên cạnh prompt?**

**Đáp:** Đó là lỗi đo riêng. FullFIFO64 V4 có26ReadTimeout, cả26ởconv30, nhóm có prompt ngắn nhất khoảng15.209token median. Gateway ghi17lần timeout khi chờ upstream và9lần client hủy. NativeLPM ưu tiên chiều dài prefix và có queue/ràng buộc khác tùy visibility; sự tập trung lỗi ở một nhóm là tín hiệu cần audit fairness, chưa đủ để quy toàn bộ nguyên nhân cho một dòng sort.

Để chấm đủ output và đo toàn bộ backlog trong V5, tất cả arm dùng cùng read/pool timeout3600giây; policy, connection limits, ngân sách KV và output cap giữ nguyên. Default lịch sử600giây vẫn được giữ để tái lập V4. Health/summary ghi timeout thật; source proof chỉ cho phép đúng các thay đổi transport/telemetry được liệt kê. Một response sau900giây dưới timeout mới không phải đã đạtSLO600giây, và lỗi V4 không bị xóa khỏi báo cáo.

**Hỏi: Vậy có đo được overlap thật chưa?**

**Đáp:** Đã đo được overlap theo thời gian giữa kernel I/O GPU-assisted và một tập kernel model trong diagnostic kernel/page_first. Có432kernel per-layer khớp12promotion×36layer; counter/event ledger khớp35,15GB payload. Hợp interval I/O dài3,120giây, giao với GEMM/GEMV/attention khoảng0,306giây, tức9,8% thời gian I/O-kernel. Tất cả interval dùng cùng clock GPU.

Đây chưa phải phần PCIe bận thuần hay số giây latency được che hữu ích. Nó cũng không thay thế diagnostic Direct: đường Direct có thiếu coverage bulk-copy trong traceMemcpy thông thường, nên DMA overlap vẫn chưa xác nhận. Off/on/off kiểm tra perturbation riêng: p95 khoảng507/518/513ms, chỉ4output token và12request mỗi phase. Bảng serving chính phải lấy từ các lượt không bật profiler.

**Hỏi: Khi một lượt đo chỉ lỗi một request thì có chạy lại riêng request đó không?**

**Đáp:** Không ghép request chạy lại vào bảng latency của lượt cũ. V5 revision1 FIFO seed102 có một `ReadError` sau6,536ms; gateway chỉ ghi59request thành công và không có request lỗi trong log. Pipeline dừng, giữ marker invalid và toàn bộ raw. Điều này phân biệt lỗi transport trước gateway với timeout dài khi request đã vào hệ thống, nhưng chưa chứng minh chính xác socket nào gây lỗi.

Revision2 dùng kết nối client mới cho mọi arm, giữ max connections256, cùng prompt/phương pháp/ngân sách và timeout3600giây. Đây là một control/mitigation cần đo lại, không phải tuyên bố đã tìm ra nguyên nhân. Cả ma trận được chạy dưới namespace mới; bốn lượt revision1 thành công cũng không được trộn vào primary revision2. Seal/plan/source revision1 được lưu theo SHA để bảo toàn lịch sử. Nếu lỗi tái diễn, tiếp tục chẩn đoán thay vì lặp retry cho tới khi bảng xanh.

### 21.1. Khi aggregate tốt hơn nhưng một nhóm bị bỏ lại

**Hỏi: Tất cả request thành công có nghĩa đã đạt SLO chưa?**

**Đáp:** Không. Full native V4 thành công1.986/1.986, nhưng chỉ1.139request, khoảng57,35%, nhận token đầu trong600giây từ scheduled arrival. Timeout của từng công đoạn không phải deadline E2E. Muốn đánh giá SLO phải định nghĩa mốc bắt đầu, deadline và mẫu số rõ ràng.

**Hỏi: FIFO full có một số chỉ số aggregate tốt hơn thì có thể kết luận công bằng hơn không?**

**Đáp:** Không. Nếu tính cả lỗi là không đạt mốc600giây, FIFO có1.794/1.986(90,33%) đạt mốc này, cao hơn native. Nhưng riêngconv30, FIFO chỉ58/105(55,24%), thấp hơn native77/105(73,33%) và có26lỗi. Các nhóm khác có thể bù aggregate, che khuất một nhóm bị chờ rất lâu. Tôi báo từng conversation, tổng lỗi và toàn bộ các mốc đã định; không lấy p95 chỉ trên1.960request thành công để tuyên bố một lượt hợp lệ.

**Hỏi: V5 đã loại bỏ mọi tradeoff latency chưa?**

**Đáp:** Chưa. Primary dev SGLang revision2 có540/540request thành công: p95 trung bình native/FIFO/union là19,043/19,163/16,803giây. Nhưng p50 native4,894giây cònunion13,564giây. Cả chín lượt đều compute69.650token; union còn có nhiều promotion hơn ở block nhỏ này. Vì vậy lời giải thích đúng không phải “luôn ít transfer/compute hơn”. Đây là tail/median tradeoff phụ thuộc engine, queue và working set; full study cùng các control mới quyết định phạm vi claim.

### 21.2. Không biến một stratum nhỏ thành kết luận toàn benchmark

Nhóm kiểm chứng abstention cố định có12QA, lấy bốn câu category5 đầu tiên theo source index ở mỗi conversation dev. Native vàunion mỗi bên chạy ba seed, tổng72request không lỗi. Mỗi lượt đều được evaluator chấm7/12, không có output chạm cap96. `answerable_f1=null` vì nhóm này không có câu có đáp án; điểm category5 được báo riêng.

**Hỏi: Có thể gọi đây là cải thiện từ0,009 lên0,583 không?**

**Đáp:** Chưa.0,009 là V4 full446câu dưới workload khác, còn0,583 là12câu của một stratum V5. Khác tập câu hỏi và lịch batching nên không phải một ablation chỉ thay template. Chúng tôi đã chứng minh prompt V5 không còn hai chỉ dẫn trái nhau, và quan sát compliance/quality trong stratum nhỏ. FullV5 vẫn cần chấm đủ mọi category để đánh giá phạm vi chất lượng.

**Hỏi: Vì sao phải giữ seed2QPS bị regression dù4QPS có gain?**

**Đáp:** Nó cho thấy policy phụ thuộc regime. Ở V5dev2QPS, p95 union thay đổi+.60/−.25/+8.54% theo ba seed; low-reuse chỉ tăng tối đa khoảng.65% và vượt gate5%. Không thể lấy control tốt để xóa control xấu. Tôi sẽ mô tả một phương pháp hữu ích có điều kiện, thay vì hứa luôn nhanh hơn ở mọi tải.

### 21.3. Đối chứng mạnh hơn và bằng chứng cấu hình thật

V5 đã hoàn tất39lượt validation SGLang,1.740request không lỗi. So nativeDFS, union giảm p95 khoảng12,1–22,9% theo seed, nhưng F1 có một cặp giảm0,0097 và hai cặp tăng. Khi tăng GPU KV lên10GiB trong control dev, p95 union lại tăng khoảng0,53–0,99%, F1 bằng nhau. Kết quả phù hợp với một lợi ích có điều kiện dưới pressure; chưa có lý do hứa thắng mọi tải hay mọi cấu hình cache.

**Hỏi: Tại sao test xanh vẫn chưa đủ chứng minh benchmark đúng cấu hình?**

**Đáp:** Test kiểm logic mà nó bao phủ. Một run còn cần actualargv, health/config và fingerprint source từ process thật. Audit V5 yêu cầu client keepalive0, read/pool3600giây, đúng policy/cap, byte budget, fresh history và source hash. Thiếu fingerprint của replay hoặc dùng transport revision cũ sẽ bị từ chối, dù các request đều trả200. Khi warmup vLLM mới chạy60/60, tôi còn kiểm subscriber có `known=true`, hash contract đã xác minh và không mất sequence. Đây mới là bằng chứng cho phép dùng actual-GPU LPM làm baseline; process sống hoặc một con sốhit không đủ.

### 21.4. TTFT tốt hơn nhưng stream có thể chậm hơn

**Hỏi: Kết quả mới nhất trên vLLM/LMCache là gì?**

**Đáp:** Ma trận V5 dev có18lượt,1.080request thành công, so sánh sáu policy qua ba lịch arrival. P95 TTFT trung bình FIFO64 khoảng35,96giây, GPU-LPM16 khoảng35,26giây, bundle16 khoảng27,47giây, union64 khoảng19,82giây. Union giảm p95 khoảng44–47% soFIFO64 và26–31% sobundle theo từng seed. Counter engine cho biết CPU KV được tiêu thụ giảm từ khoảng918nghìn xuống84nghìn token mỗi lượt; đây là cơ chế khác rõ với nativeSG, nơi compute bằng nhau và promotion của union còn cao hơn.

Tôi chưa gọi đây là kết quả toàn LoCoMo: dev chỉ có60câu hỏi cố định. Full1986QA, chất lượng từng nhóm và fairness vẫn phải kiểm. F1 trung bình union khoảng.3184, FIFO.3139, bundle.3172; các giá trị gần nhau không chứng minh hai hệ thống tương đương chất lượng.

**Hỏi: Có phải chỉ đẩy công việc sang sau token đầu để lấy TTFT đẹp?**

**Đáp:** Đây là câu cần kiểm trực tiếp. Tôi đo thêm từ scheduled arrival đến lúc response đóng. P95 completion trung bình FIFO64/bundle/union lần lượt36,45/28,04/21,27giây; union vẫn cải thiện khoảng40–43% soFIFO ở từng seed. Vì vậy lợi ích dev không chỉ nằm ở token đầu.

Nhưng trải nghiệm streaming có đánh đổi khác. Proxy thời gian trung bình mỗi token của từng request là `(thời điểm đóng response − thời điểm text đầu tiên)/(số output token − 1)`. P95 của proxy, lấy trung bình ba lượt, tăng từ19,38ms/token của FIFO64 lên117,67ms/token của union; bundle khoảng52,27. Một hệ thống có thể bắt đầu và kết thúc sớm hơn nhưng các token ở giữa giãn hơn. Chưa đo đủ để quy nguyên nhân cho một kernel cụ thể; concurrency, prefill/decode interference, batching và output khác nhau đều cần xem.

**Hỏi: Vì sao không gọi117,67ms là p95 ITL?**

**Đáp:** Vì phép tính đã lấy trung bình trong từng request rồi mới lấy p95 giữa các request. ITL đo khoảng cách giữa hai token liên tiếp; hai phân phối có đơn vị quan sát khác nhau. Client còn nhận stream theo chunk, có thời gian metadata/đóng response và cách đếm special token. Request chỉ có một token bị loại khỏi proxy, không gán0để làm đẹp bảng. Không lưu từng timestamp token thì không thể dựng lại chính xác ITL sau này.

Với full study, một observer bổ sung chụp native ITL histogram trước/sau mỗi lượt. Chỉ chấp nhận khi clock nằm ngoài cửa sổ request, PID không đổi và tổng prompt-token tăng đúng ledger. Histogram chỉ cho khoảng chứa quantile theo ranh giới bucket; không tự nội suy thành một p95 chính xác. Thiếu coverage thì ghi null. Đây là quan sát nhẹ qua metrics endpoint, không bật GPU profiler trong bảng latency chính.

**Hỏi: Vậy khi chọn policy cho sản phẩm, nên tối ưu chỉ số nào?**

**Đáp:** Tùy yêu cầu: người dùng chat quan tâm cả lúc bắt đầu lẫn độ đều của stream; tác vụ batch có thể quan tâm completion và throughput hơn. Tôi sẽ đặt deadline TTFT, completion và streaming cụ thể, kiểm tỉ lệ đạt từng yêu cầu trên mọi request, rồi xem từng conversation. Không chọn policy chỉ vì một ô p95 tốt; một nhóm bị bỏ lại hoặc stream chậm hơn có thể làm policy không phù hợp sản phẩm.

### 21.5. Ba seed không phải hàng trăm thí nghiệm độc lập

**Hỏi: Có180request mỗi policy thì confidence interval đã chắc chưa?**

**Đáp:** Chưa. Đó là60câu hỏi chạy lại theo ba lịch arrival; request trong một lượt dùng chung engine, cache, batch và queue. Nếu bootstrap180request như180thí nghiệm độc lập sẽ đánh giá thấp bất định. Tôi báo delta từng cặp seed trước, sau đó thêm interval thăm dò trên ba log-ratio của run. Giả định độc lập/phân phối của mô hình thống kê chưa được xác minh với n=3, nhất là khi tái sử dụng process.

Ví dụ SGnative4QPS có ba delta p95 đều âm, nhưng interval thăm dò khoảng[−24,37%,+3,25%] vẫn qua0. MainFIFO64 khoảng[−49,11%,−40,28%] hẹp hơn trong điều kiện đã đo. Không dùng hai interval này để tuyên bố chắc chắn cho host khác, câu hỏi mới hoặc chất lượng tương đương. Control full một seed không được gắn interval ba seed từ dev.

**Hỏi: Có thể lấy trung bình p95 của các run thay cho p95 của toàn bộ request không?**

**Đáp:** Có thể báo trung bình p95 nếu ghi đúng tên và mục đích: nó tóm tắt các lượt đo. Nó không bằng p95 khi gộp request. Tôi giữ cả quantile từng run, paired delta và định nghĩa aggregate trong artifact để reviewer tái tính. Tương tự, throughput tính bằng tổng output token chia toàn thời gian workload có thể bị giới hạn bởi lịch arrival; không tự gọi đó là capacity tối đa của engine.

### 21.6. Nêu đóng góp mà không vượt bằng chứng

**Hỏi: Nếu trình bày project trong hai phút, nên nói gì ở checkpoint này?**

**Đáp:** “Tôi nghiên cứu admission cho conversational QA có prefix dài và working set lớn hơn GPU KV. Tôi xây policy gom reuse bằng union các block prefix, giữ ngân sách và giới hạn bypass để tiến triển. Tôi đo trên vLLM/LMCache và native HiCache, với baseline FIFO, GPU-LPM thật, bundle, fixed DHAS và native LPM/DFS cùng một component guard. Tôi kiểm nguồn KV và budget bằng byte, giữ cả failed runs, chấm câu trả lời bằng evaluator cố định. Dev cho lợi ích tail rõ trên main stack, nhưng nativeSG có median penalty và lower-load regression; streaming proxy của main cũng xấu hơn. Tôi đang kiểm full benchmark trước khi chốt phạm vi đóng góp.”

Điểm cần tránh là nói đã triển khai đầy đủ Strata hoặc đã thắng mọi baseline mới. Component guard chỉ chuyển thể một phần, SGLang version được pin vì tương thích môi trường, và các policy upstream mới chưa được đo phải ghi rõ. Một kết quả có điều kiện, có cơ chế đo được và giới hạn trung thực sẽ chịu được câu hỏi sâu hơn một lời hứa thắng mọi trường hợp.

**Hỏi: Native ITL histogram có định nghĩa giống nhau giữa hai engine không?**

**Đáp:** Không được mặc định như vậy. Source SGLang0.5.14 lấy thời gian từ lần cập nhật trước chia số token mới, rồi cộng số token đó vào bucket chứa giá trị trung bình. Nếu một cập nhật có nhiều token thì histogram không biết timestamp riêng của từng token. Source vLLM0.22.0 ghi khoảng giữa các output-update timestamp từ engine core sau prefill. Cả hai đều khác clock nhận chunk của client. Tôi lưu SHA source và mô tả trong `results/v3/v5_native_itl_semantics.json`, so policy trong từng engine và không gộp hai histogram thành một bảng xếp hạng token latency.

**Hỏi: Làm sao chứng minh không chỉ chuyển queue từ engine ra gateway?**

**Đáp:** Tôi giữ scheduled arrival làm mốc chung, tái dựng từng request qua nhận ở gateway, chuẩn bị, chờ admission, upstream token đầu rồi client nhận text đầu. Tổng các đoạn khớp arrivalTTFT trong sai số nhỏ hơn1e-6ms ở cả39gateway arm của validation. MainFIFO64 có meanTTFT25,45giây; union15,25giây dù khoảng11,87giây nằm ở admission. Lợi ích tổng vẫn còn. Nhưng SGnative mean7,16giây cònunion13,30giây, nên tail tốt hơn không đủ để gọi trải nghiệm trung bình tốt hơn. Tôi cộng thời gian từng request hoặc mean của các đoạn, không cộng p95 các đoạn vì request ở p95 của mỗi đoạn có thể khác nhau. Đoạn upstream vẫn gồm queue, copy, compute và transport; chưa có GPU timeline thì không được gọi đó là GPU compute thuần.


### 21.7. Healthcheck xanh nhưng request không tiến triển

**Hỏi: Có thể tin `/healthcheck` trả200 là engine đang xử lý tốt không?**

**Đáp:** Không. Trong main repeat V5 seed702, gateway đã hoàn tất27request nhưng còn11đang chờ upstream và2chờ admission. Chuỗi metrics hơn6phút ghi GPU0%, engine0running/11waiting, KV khoảng99,7% và counter prompt/compute/TTFT không đổi. LMCache vẫn báohealthy, không cóL1read/write lock hay công việc store/prefetch đang chờ. Health của HTTP/server khác với liveness của toàn bộ request pipeline.

Tôi giữ đây là quan sát một lượt chưa kết thúc, không tự gắn nhãn nguyên nhân. Source cho thấy async restore và delayed block freeing có thể giữ tài nguyên ở các trạng thái ngoài “running”; cần state/future cụ thể để chứng minh. Logical union của prefix cũng không tự bảo đảm mọi physical block đã chia sẻ được trong lúc restore. Chưa có bằng chứng để gọi đây là deadlock do một dòng code, do dung lượng CPU hay do scheduler riêng của chúng tôi.

**Hỏi: Xử lý một lượt mắc kẹt mà vẫn giữ benchmark trung thực thế nào?**

**Đáp:** Lưu clock/counter/PID và số request đã hoàn tất, giữ timeout như protocol, chờ kết quả terminal hoặc ghi rõ một lần dừng thủ công nếu phải dừng. Không lấy27response thành công tính p95 của một workload40request, không retry13request rồi ghép vào lượt cũ. Snapshot thread/diagnostic là bằng chứng chẩn đoán riêng; không trộn với bảng performance không profiler. Nếu cần sửa admission hoặc connector, phải có protocol/source mới, kiểm chứng rồi đo lại dưới namespace mới.

**Hỏi: Vì sao so đúng flag byte rồi vẫn sai dung lượng thực tế?**

**Đáp:** Flag đi qua nhiều lớp. LMCache đọcGiB thành byte chính xác nhưng allocator lazy lại làm tròn heap lên bội64MiB. Vì vậy16.000.745.472byte cấu hình thành16.039.018.496byte thật trên process đang đo. NativeHiCache làm tròn theo page16token, khác granularity. Tôi phải đọc status/allocator source và ghi riêng requested, allocated, usable capacity; không dùng argv đúng để suy ra actual heap đúng. Sai lệch nhỏ này không tự chứng minh nguyên nhân stall. Nó sửa phạm vi claim resource parity; so policy trong cùng engine vẫn dùng cùng heap.

**Hỏi: Kết quả lặp trên các câu hỏi khác dev có giữ nguyên độ lớn lợi ích không?**

**Đáp:** Không. Phần nativeSG của repair repeats đã audit18lượt/720request không lỗi. So nativeLPM4QPS, union giảm p95 khoảng11,22/7,81/4,34% theo ba seed, nhưng median tăng khoảng38–40%; một seed giảmF1. Đây là40câu conv43/44đã từng dùng ởV4, không phảiholdout mới. SoDFS mức giảm p95 khoảng11,00/9,83/4,40%. Tôi báo hiệu ứng nhỏ hơn dev này cùng với main đang mắc kẹt, không chọn bảng dev tốt nhất làm kết luận. Audit toàn27lượt và full study vẫn chưa đủ, nên ở checkpoint này chưa thể tuyên bố đóng góp đã đạt mục tiêu.


### 21.8. Vì sao manual abort không được gọi là timeout tự nhiên?

Main repeat V5 seed702đã đứng yên gần29phút: GPU0%, engine0running/11waiting, KV99,7%, counter compute/prompt/TTFT không đổi. Sau khi chuyển cả lượt thành diagnostic, tôi ghi thời điểm can thiệp và dừng gateway để client xuất đủ40kết quả. Có27response thành công và13`RemoteProtocolError` sau can thiệp; output hash của cả40record được kiểm. Conv43thành công18/20, conv44thành công9/20. Không tính p95 chỉ trên27response, cũng không gọi13lỗi là timeout3600giây hay lỗi mạng tự nhiên.

**Hỏi: Tại sao không tiếp tục tăng timeout?**

**Đáp:** Timeout dài hơn không tự tạo tiến triển khi engine không thực hiện công việc. Tôi đã giữ nguyên3600giây trong lượt gốc, loại lượt khỏi performance và ghi rõ manual abort, thay vì chờ thêm rồi chọn số đẹp. Diagnostic kế tiếp dùng180giây đồng nhất cho cảoff/on/off, có ID riêng và không đi vào bảng benchmark. Mốc180giây là cách giới hạn thời gian chẩn đoán, không phải sửa SLO hay chứng minh policy đạt deadline đó.

**Hỏi: Tại sao replay cả ba arm trước seed702thay vì chỉ chạy request lỗi?**

**Đáp:** Engine và connector giữ trạng thái qua nhiều lượt ngay cả khi đã reset cache. Nếu lỗi phụ thuộc trạng thái tích lũy hoặc thứ tự, chỉ chạy riêng request có thể làm nó biến mất. Diagnostic prospectively đăng ký đúng warmup→FIFO701→bundle701→union701→union702, lặp off/on/off với process mới cho mỗi phase. Probe ghi status request, block vật lý/refcount và membership của future, không thêm CUDA synchronization. Nó giúp phân biệt logical prefix có vẻ fit với tensor/block đã thật sự chia sẻ và được giải phóng; chưa có snapshot thực tế thì các lời giải thích đó vẫn chỉ là giả thuyết.

## 22. Khi logical sharing chưa trở thành physical sharing

**Hỏi: Union các block prefix giống nhau có đủ dự đoán memory footprint không?**

**Đáp:** Không ở mọi trạng thái. Nó tính đúng lượng thông tin KV có thể dùng chung, nhưng engine có thể cấp phát nhiều bản vật lý khi restore còn bất đồng bộ và các block chưa được đăng ký sẵn sàng trong cache index. Trong diagnostic native, hai request cùng prefix đang`WAITING_FOR_REMOTE_KVS` mỗi request có1.776block. Có856block dùng chung, còn920logical prefix block được cấp phát ở hai bộ block ID khác nhau. Thực tế là2.696block vật lý thay vì1.776nếu chia sẻ trọn vẹn.

Mỗi block16token của model4B chiếm`16×147456`byte, nên920bản cấp phát thêm là2.170.552.320byte, khoảng2,021GiB. Pool2730block được đối chiếu thành2696đang được request giữ+33free+1null. Đây là ledger allocation/refcount, không phải suy luận từ một con sốcache-hit. Hai request mỗi bên còn920block chưa được hash vào cache; snapshot worker gần đó có2retrieve future. Không đọc tensor nên chưa khẳng định hai buffer chứa dữ liệu gì hoặc mọi copy đã hoàn tất.

**Hỏi: Có tìm được nguyên nhân stall trước đó chưa?**

**Đáp:** Chưa. Cả ba phase off/on/off mới đều hoàn tất, tổng660request không lỗi. Snapshot trùng block xảy ra ở baseline bundle rồi tự phục hồi; các điểm lấy mẫu union/target trong lần diagnostic này ghi0trùng. Nó chứng minh một khoảng cách giữa logical và physical sharing, chưa chứng minh đó gây stall gốc. Tôi giữ nguyên lần stall thật và13gián đoạn do manual abort, không dùng ba lần thành công để xóa nó.

**Hỏi: Thay đổi admission đang kiểm tra là gì?**

**Đáp:** Tôi giữ union budget và giới hạn bypass, thêm gate: khi đã có một request cùng exact prefix chưa ra text đầu tiên, follower đó tiếp tục chờ; request prefix khác vẫn có thể được xem xét trong bound. Khi producer ra text đầu tiên, follower có thể tiếp tục. Sau đó mỗi prefix vẫn chỉ có tối đa một request mới chưa ra text đầu tiên tại một thời điểm. Mục tiêu là giảm các producer/follower cùng đi vào giai đoạn restore chưa sẵn sàng; chưa có GPU result thì đây vẫn là giả thuyết đang kiểm.

Tôi thêm baseline`ready_fifo`có cùng gate/bypass nhưng không có union budget. Nếu nó tốt ngang hoặc hơn candidate, phải thừa nhận phần lợi ích đến từ readiness đơn giản, không tự gán cho union. Baseline FIFO và union cũ vẫn được đo lại trong pilot. Các đối chứng mạnh khác, controls và full benchmark còn phải hoàn tất trước khi chốt đóng góp.

**Hỏi: First text có bảo đảm KV đã được pin sẵn cho follower không?**

**Đáp:** Không. Nó là tín hiệu frontend sau khi model đã bắt đầu phát text, không phải API cấp phát/pinning. Native cache publication, eviction, request completion và queue có thể làm giả định sharing thay đổi. Gate chỉ bảo đảm quy tắc số request pending trong mô hình admission; không bảo đảm engine luôn tiến triển, không cưỡng bức restore/recompute và không đưa ra deadline E2E. Cần counter/allocation evidence và kiểm lỗi/fairness thực tế để xác định phạm vi.

**Hỏi: Vì sao thêm một gate nhỏ lại phải sửa decision-cache key?**

**Đáp:** Trước đây queue và tập active không đổi thì quyết định có thể cache lại. Với readiness, producer có thể vừa ra text đầu tiên mà cả hai tập ID vẫn giữ nguyên. Nếu cache key chỉ chứa ID, scheduler có thể giữ quyết định`None`cũ mãi và không dispatch follower dù điều kiện đã đổi. Tôi đưa bit readiness của từng active request vào key, đồng thời dùng notification hiện có khi nhận first text. Test kiểm quyết định bị cache lúc pending rồi follower được đánh thức sau transition; test khác kiểm cancellation và bypass/drain. Test này xác minh logic, không thay thế GPU benchmark.

**Hỏi: Vì sao71unit test xanh mà policy mới vẫn chưa chạy được?**

**Đáp:** Test trước đó kiểm class scheduler và factory adapter, nhưng chưa đi hết chuỗi launcher. CLI replay còn danh sách policy cố định nên nó từ chối hai tên mới trước khi gửi request. Tôi giữ lần pilot hỏng, lưu nguyên source đã đăng ký và không lấy hai baseline thành công ghép với một lượt sửa sau. Bản thay thế có namespace mới, thêm preflight cho CLI và test so sánh launcher/replay với parent: chỉ khác tên module/entrypoint và hai enum metadata. Toàn bộ72test hiện qua; vẫn phải nhìn request thật, source/argv thực tế và audit toàn bộ pilot mới biết end-to-end đã đúng. Test xanh không tự chứng minh một thí nghiệm hoàn tất hay một method có lợi.

**Hỏi: Pilot có chứng minh gate mới nhanh hơn union cũ không?**

**Đáp:** Chưa. Pilot mới có400/400request thành công trên hai tập đã dùng trước đây. Gatedunion giảm p95 khoảng41–45%soFIFO, nhưng so union cũ thì dev chậm hơn3,2%, stress nhanh hơn2,6%. Gate-onlyFIFO gần như giữ nguyên compute/CPU-source work và latency củaFIFO; phần lợi ích lớn hiện đến từ grouping/union. Gate là giả thuyết bảo vệ trạng thái pending, chưa chứng minh sửa được stall gốc. F1 soFIFO giảm nhỏ ở cả hai tập và khác chiều khi so union cũ, nên không gọi quality equivalence.

**Hỏi: Tại sao vẫn đo decode khi TTFT giảm gần một nửa?**

**Đáp:** Vì người dùng nhìn cả stream. Proxy decode p95 của gatedunion giảm so union cũ từ123xuống92ms/token ở dev và90xuống52ởstress, nhưng FIFO chỉ khoảng19/18ms/token. Completion dev lại tăng từ21,4lên22,4giây, trong khistressgiảm21,0xuống19,4. Cần báo cả gain và cost. Đây là proxy theo request, chịu ảnh hưởng output length/chunk/đóng response; tôi bổ sung native histogram ở các lượt chưa chạy để đối chiếu. Không có baseline snapshot của hai arm đầu thì đểnull, không dựng lại từ số trung bình của arm khác.

**Hỏi: Vì sao ma trận tiếp theo khởi động engine mới cho mỗi arm?**

**Đáp:** Để tách các lượt đo khỏi trạng thái tích lũy qua reset sau khi đã thấy một anomaly chưa giải thích. Mọi baseline/candidate đều chịu cùng quy tắc, có warmup giống nhau và thứ tự cân bằng theo seed. Nó làm đơn vị lặp có process mới, nhưng không chứng minh lỗi đã được sửa hay production service chạy lâu sẽ an toàn. Full workload vẫn phải chạy hàng nghìn request trong một lượt. Tôi giữ dữ liệu protocol cũ riêng, báo stage mới là development, rồi tiếp tục native/control/full evaluation trước khi chốt đóng góp.

**Hỏi: Có thể thêm một cột metadata rồi tiếp tục append CSV cũ không?**

**Đáp:** Không an toàn nếu writer vẫn ghi theo thứ tự field của schema mới nhưng header cũ không đổi. Project có CSV main header35cột và65dòng về sau có38cột khi thêm timeout/keepalive. Đọc bằng header cũ có thể gán nhầm giá trị cho cột. Tôi giữ bản raw, lấy các JSON summary có tên key rõ ràng làm nguồn rồi tạo index CSV riêng với union header, summary SHA và invalid status. Các latency quantile của run lỗi/invalid được để trống trong index; raw không bị sửa. Test kiểm đúng trường thiếu, metadata mới và bảo toàn file cũ. Index không tự biến một run thành hợp lệ: vẫn phải qua audit đúng protocol, nhất là các lỗi xảy ra trước khi client tạo summary.

**Hỏi: Fresh engine cho mỗi arm và fresh engine cho mỗi block khác nhau thế nào?**

**Đáp:** Với main matrix V6, mỗi policy/seed có engine riêng, nên không dùng lại trạng thái native của policy trước đó. Với native validation tiếp theo, mỗi regime/seed có engine mới nhưng các policy trong block dùng chung process, có flush cache và gateway mới giữa các arm. Cách thứ hai giảm chi phí khởi động và tạo paired comparison trong cùng process, nhưng vẫn có thể giữ trạng thái allocator/kernel sau flush. Tôi đảo thứ tự và ghi PID, không gộp hai protocol thành một quần thể. Cả hai đều chưa chứng minh service chạy lâu không bị stall.

**Hỏi: Counter không xuất hiện ở warmup có được xem bằng 0 không?**

**Đáp:** Không. Prometheus có thể chỉ tạo một metric khi sự kiện đầu tiên xảy ra. Nếu đầu cửa sổ không có cached-token counter, giá trị cuối không đủ chứng minh delta của toàn cửa sổ bằng bao nhiêu. Collector V6 lưu null và hai endpoint riêng; warmup được đánh dấu tường minh, không dùng để claim hiệu năng. Các lượt đo chính thức phải đủ counter để đối chiếu cached+uncached với toàn bộ prompt. Với ITL, nếu snapshot thiếu, PID đổi, lệch cửa sổ hoặc histogram reset, kết quả coverage phải fail và mean/bounds để null. Một số đo thiếu không tự làm các request thành lỗi, nhưng cũng không được thay bằng số từ lượt khác.
