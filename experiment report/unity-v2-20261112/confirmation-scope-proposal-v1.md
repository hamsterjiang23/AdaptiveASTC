# 确认集10张近重复候选的范围修订提案

## 身份元数据核验

用户授权只读核验确认名单、身份哈希与既有近重复关系。10份元数据的SHA-256复核通过，2000张确认图在冻结预留名单与采集清单中的顺序、源MD4、源SHA及meta SHA一致，13000张图在精确RGBA与近重复审计中的身份字段一致。完整结果见[身份元数据复核](confirmation-identity-metadata-review-v1.json)。`[verified: confirmation-identity-metadata-review-v1.json authorization、metadata_files_verified、ordered_capture_reservation_identity_matches、ordered_exact_near_audit_identity_matches]`

精确RGBA跨确认／开发重复组为0；同尺寸、同坐标RGBA的既有RMSE≤2/255关系共有11条，涉及10张确认图和11张训练图。第1371个确认位置对应两条训练关系。下表RMSE以8-bit像素值为单位。`[verified: confirmation-identity-metadata-review-v1.json exact_confirmation_development_duplicate_groups、same_size_aligned_rgba_threshold_8bit、near_confirmation_training_pair_records、affected_confirmation_images、related_training_images、proposed_replacements[6].relations]`

## 逐位置替换方案

按受影响的主名单位置排序，依次使用冻结备用名单的前10张。表中位置从1开始，表内使用文件名；完整资产路径、训练侧关联路径、源SHA-256、字节数、meta SHA-256及原排序rank保存在结构化结果的`proposed_replacements`中。`[verified: confirmation-identity-metadata-review-v1.json proposal_policy、proposed_replacements]`

| 主名单位置 | 拟移出的确认图 | 既有RGBA RMSE | 备用位置 | 拟补入图 | 依据 |
|---|---|---|---|---|---|
| 25 | `Atlas_CollectorDraw_Valentine_06_add_main.jpg` | 1.540886 | 1 | `Atlas_ActivityWOF02_add.png` | `[verified: confirmation-identity-metadata-review-v1.json proposed_replacements[0]]` |
| 29 | `Ground_03.jpg` | 1.013341 | 2 | `ML_M02_068_S4_hedaobake_03.tga` | `[verified: confirmation-identity-metadata-review-v1.json proposed_replacements[1]]` |
| 59 | `PartyGame_Play_Mask2.tga` | 0.167377 | 3 | `2.png` | `[verified: confirmation-identity-metadata-review-v1.json proposed_replacements[2]]` |
| 168 | `Atlas_Map1900291_MC_mask.png` | 0.888092 | 4 | `PVP_MLBC_AS_WHM_01.png` | `[verified: confirmation-identity-metadata-review-v1.json proposed_replacements[3]]` |
| 760 | `ML_049_S4_hedaobake_new02_06.tga` | 1.591107 | 5 | `guangquan_sanxing_S7830_cns.png` | `[verified: confirmation-identity-metadata-review-v1.json proposed_replacements[4]]` |
| 1314 | `ML_049_S4_hedaobake_new02_03.tga` | 0.917313 | 6 | `Atlas_ShareBackground26_add.png` | `[verified: confirmation-identity-metadata-review-v1.json proposed_replacements[5]]` |
| 1371 | `PVP_MLBC_041_003_04_low.png` | 1.323129／0.951587 | 7 | `pic_mmrframe05.png` | `[verified: confirmation-identity-metadata-review-v1.json proposed_replacements[6]]` |
| 1384 | `skillIndicator_SkillAreaAndJiantou_Hero131_Skill1013110.png` | 1.341124 | 8 | `yun03.png` | `[verified: confirmation-identity-metadata-review-v1.json proposed_replacements[7]]` |
| 1549 | `Atlas_LoadingGuideBg_MC_mask.png` | 0.535332 | 9 | `Atlas_GiftShow03_add.png` | `[verified: confirmation-identity-metadata-review-v1.json proposed_replacements[8]]` |
| 1732 | `FrigidseaMode_default_LM0_mask.tga` | 0.114803 | 10 | `Soft.psd` | `[verified: confirmation-identity-metadata-review-v1.json proposed_replacements[9]]` |

内存中的方案核验得到2000个唯一资产路径和源MD4，1990个位置与原名单逐项相同；应用方案将消耗10张备用图，剩余431张。当前审计图中的已知11条训练—确认关系将随这10张图移出而解除。10张补入图的原生像素隔离仍待采集和完整复审。`[verified: confirmation-identity-metadata-review-v1.json in_memory_proposal_checks]`

10张补入图的身份均与冻结备用项逐字段匹配，源路径和MD4与现有13000张审计记录无重合，直接父目录与开发集无匹配。5张补入图与现有确认图处于同一直接父目录，具体位置已作为诊断记录。`[verified: audit_confirmation_identity_metadata_v1.py run；confirmation-identity-metadata-review-v1.json proposed_replacements[].same_direct_parent_as_existing_primary_positions、same_direct_parent_as_development]`

## 本轮执行记录

本轮模型调用、训练更新、编码次数均为0，源图／参考像素／ASTC文件访问为0，模型／预测文件访问为0，cohort_modified=false、test_opened=false。SHA错误、备用顺序错误及越界图像读取请求均在小样本守卫检查中被拒绝，全部绑定元数据在核验结束时再次通过SHA复核。`[verified: confirmation-identity-metadata-review-v1.json model_forward_calls、training_updates、actual_encoding_calls、source_image_or_pixel_payload_files_opened、model_or_prediction_files_opened、cohort_modified、test_opened、guard_checks]`

原提案记录的10张源文件／meta检查均通过，该记录形成于此前核验。本轮复核了记录文件身份，源图和meta文件当前字节的重新验证属于后续补采阶段。`[verified: confirmation-identity-metadata-review-v1.json historical_source_file_checks、proposed_replacements[].historical_source_check_receipt]`

首次结构检查额外显示了采集清单首条记录的既有选参字段，修订选择仅使用身份和近重复关系。初版审计还把确认集内部同父目录作为拒绝条件，现已按冻结cohort规则改为诊断记录，开发集父目录匹配单独统计。`[verified: confirmation-identity-metadata-review-v1.json initial_structure_preview_included_first_capture_native_selection、selection_uses_model_predictions_quality_or_native_labels、diagnostic_correction]`

## 待批准的执行范围

建议批准本表10个位置的修订、10张补入图的Unity原生补采，以及修订后10000／1000／2000图的完整身份与像素复审。补采应核验实际导入类型、参考像素、回调身份和原搜索标签，以新cohort身份绑定完整2000张确认图。`[opinion]`

该范围涉及图像读取和原生采集编码，超出本轮只读元数据授权。后续计划将模型调用与训练更新设为0，并在像素／采集证据准备完成后另行取得正式独立确认执行授权。`[verified: confirmation-identity-metadata-review-v1.json authorization、future_scope_decision、future_formal_confirmation_execution_authorized、future_requirements]`
