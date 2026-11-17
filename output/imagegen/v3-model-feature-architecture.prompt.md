# V3模型特征叠层架构图生成提示词

## 生成方式

使用内置 image_gen.imagegen。工具接口未提供模型版本选择或可核实的模型版本回执。用户指定的 gptimage2.5 版本未核实。

参考图为用户提供的ResNet特征叠层样式图。以下三次调用构成最终图像的生成链。

## 基础生成

Generate a fresh, technically accurate scientific NEURAL NETWORK ARCHITECTURE FIGURE. Use the supplied image ONLY as a visual style reference: perspective stacks of translucent feature-map planes, blue-to-green-to-orange color coding, shrink spatial size and increase visible stack depth, residual skip arcs, fine lines, pure white background. Chinese headings and concise English tensor labels. Large readable text. Landscape high-resolution illustration, approximately 3200×1800. It should look like a paper's illustrated ResNet architecture, not a flowchart of rectangular cards.

Title "当前 ASTC 质量预测网络"
Subtitle "ResNet-34 · 5通道图像输入 · 8维属性融合 · 双预测头"

FOCUS ON THE NEURAL NETWORK ONLY. End at the three correct neural prediction tensors. Do not draw the real ASTC encoder, a PSNR postprocessor, a candidate table, a bottom pipeline, or long outer loops. This restriction is essential to maintain clean accurate wiring.

FLOW AND EXACT STRUCTURE:
A. Main visual left to right. Input: an illustrative green game texture tile with one highlighted patch, labeled "Unity参考图 RGBA", "P个240×240 patch". Then FIVE colored/grayscale stacked planes with individual labels "R", "G", "B", "A", "M". M means valid pixel mask. Group label "RGBA + valid mask", "5×240×240". Tiny text "RGBA → [-1,1]". Show a clear arrow into the backbone.
B. Backbone sequence of stacked feature planes:
"7×7 Conv s=2 / BN / ReLU" and "64×120×120"
then "MaxPool s=2"
then four distinctive stacked groups:
"BasicBlock×3" / "64×60×60"
"BasicBlock×4" / "128×30×30"
"BasicBlock×6" / "256×15×15"
"BasicBlock×3" / "512×8×8"
Connect every stage by a directional arrow. Show residual skip arcs with small plus signs around the BasicBlock groups as in the reference. Small caption "BasicBlock = 两层3×3卷积 + 残差相加".
C. Arrow from last stage into "mask加权空间池化", then a visible purple feature vector labeled "f · P×512". The valid mask M also feeds the pooling by a thin dotted purple bypass, ending AT THE POOLING, not at f.
D. Under the backbone, show a clearly labeled "8维属性" vector with small two-line list:
"log₂W, log₂H, srgb, normal"
"need_alpha, alpha_constant, normal_metric_mips, black_ratio".
An arrow from this vector goes to "Linear 8→1024", then to two visible half-vectors "gain 512" and "offset 512".
E. Use ONE concise fusion panel rather than individual arithmetic circles. This panel MUST have THREE incoming arrows: from f, from gain, from offset. In the panel write the EXACT formula:
"f′ = f ⊙ (1 + gain) + offset"
Its one output is a purple feature vector labeled "f′ · P×512". This f′ output must clearly branch into the TWO prediction paths below. Keep the f→fusion arrow continuous and clearly visible.

TWO PATHS BOTH START AT f′, NEVER AT offset OR METADATA:
Path A, upper:
"patch误差头"
"Linear 512→80"
then show a 3D prediction tensor with exact label:
"P×20×4"
"RGBA log-MSE"
This tensor is a TERMINAL OUTPUT, without outgoing arrows.

Path B, lower:
"同图patch加权均值" / "512维".
Then CONCAT this 512-dimensional image vector with a DIRECT 8-dimensional metadata vector from D. Show a visible concatenation bracket with the exact arithmetic "512 + 8 = 520". The direct metadata connection must be a separate line from the metadata vector to this concat.
Then "整图头" / "Linear 520→140".
This head splits into exactly TWO terminal prediction tensors:
1. "20×4" / "零误差 logits" / "80 values".
2. "20×3" / "整图质量 · Softplus" / "MS-SSIM dB / 法线mean° / 法线P95°".
These two tensors are TERMINAL OUTPUTS, without outgoing arrows. Do NOT connect either terminal output to the other output or back into the backbone.

Label the group of three prediction tensors "网络输出". Add a small legend beneath them "20候选 = 4种Blocksize × 5档Quality".
At bottom only a simple one-line factual caption, with no arrows:
"网络预测候选质量，外部规则据此选择Blocksize与Quality起点。"
And a small note "特征叠层为示意，数值为实际张量维度。"

PLAN THE SPACING BEFORE RENDERING. The backbone should be the largest pictorial component and flow across the upper/middle canvas. Put metadata below it. Place the fusion after the pooled backbone feature. Place the two prediction paths in clear upper/lower lanes after the fusion. Use whitespace to keep three fusion inputs and the metadata concat input unambiguous. The exact correctness of arrow endpoints is more important than extra decoration. Use clean vector-like typography, no logos, watermark, decorative numbering, fake accuracy numbers, 1000-class classifier, animal class, attention module, decoder, extra MLP hidden layers, or mean-max image pooling.

## 局部修正

Make ONLY THREE small local corrections to this existing architecture image. Preserve the complete layout, all arrows and their endpoints, fusion formula, feature-map stacks, other text, and both output branches exactly.

1. The input channel stack currently contains six plates because A is duplicated. Replace this local input stack with EXACTLY FIVE translucent planes, each labeled ONCE in this order: R, G, B, A, M. R red, G green, B blue, A light gray, M dark-gray border with white interior. The group label must remain "RGBA + valid mask" and "5×240×240". Reattach the existing dotted mask connector to the M plane without changing its endpoint at mask-weighted pooling.

2. Correct the dimension directly beneath the ORANGE "BasicBlock×6" heading. It is currently wrong. Replace ONLY that dimension line with the exact text "256×15×15". The full four stage dimensions from left to right MUST read "64×60×60", "128×30×30", "256×15×15", "512×8×8". Keep all stage headings and stacks unchanged.

3. The small upper prediction head says "pach误差头". Correct it to the exact text "patch误差头", preserving its second line "Linear 512→80".

Make no other changes. Keep the original sharp white-background academic figure.

## 通道示意与阶段标签修正

Edit this supplied neural-network figure with two highly localized simplifications to ensure the illustration's technical labels are exact.

CHANGE A — INPUT ILLUSTRATION:
Erase and redraw the entire small channel-stack area between the green input texture and the first 7×7 convolution (the rectangle approximately x=220..420, y=220..445 in the supplied image).
Replace the current individual six cards with ONE compact isometric cuboid divided into EXACTLY FIVE clearly separated colored channel slabs. Its five visible band labels must be, once each, "R", "G", "B", "A", "M", in that order. Use red, green, blue, light gray, purple for these five slabs. There are FIVE slabs total. The top group caption stays "RGBA + valid mask" and "5×240×240". The M slab alone connects to the existing dotted purple mask-pooling bypass. The cuboid's main output connects to the existing convolution arrow. Keep all other layout unchanged.

CHANGE B — SIMPLIFY ONLY FOUR RESIDUAL-STAGE SIZE SUBTITLES:
Leave the four BasicBlock headings exactly "BasicBlock×3", "BasicBlock×4", "BasicBlock×6", "BasicBlock×3".
Replace their second text lines, respectively, with ONLY the following four exact labels:
"64 channels"
"128 channels"
"256 channels"
"512 channels"
Remove the old C×H×W dimension text under these four headings. Each subtitle must show only the channel count and the word channels. This avoids overly small spatial labels. Do not change the convolution stem's "64×120×120" label or any other tensor sizes elsewhere.

Everything else MUST STAY THE SAME: all arrow endpoints, the f→affine-fusion connector, gain and offset inputs, direct metadata→Concat connection, f′ branching, both prediction heads, all three terminal outputs, metadata fields, title and all other text. Preserve the existing high-quality white-background vector-like scientific illustration, crisp typography, feature-map stacks, and colors.

