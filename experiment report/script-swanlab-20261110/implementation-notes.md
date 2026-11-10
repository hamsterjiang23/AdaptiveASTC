# Script launchers and SwanLab integration

## Deviations

- 启动入口统一放在script/，核心配置、训练与跟踪逻辑继续由src中的class维护。`[verified: 用户要求“用脚本启动的脚本全部放到script里面”；opinion: 职责分配]`
- 训练脚本使用TOML集中配置，既有Trainer构造参数与CLI调用通过兼容入口衔接。`[opinion]`
- 使用现有HAMSTER登录和AdaptiveASTC项目，真实云端验证包含既有两组30轮实验的历史导入，保留来源SHA与historical_import标记。`[verified: 本次verify与云端info、summary输出]`

## Discovered edge cases

- 初始依赖中无SwanLab，API key环境变量为空。uv安装0.10.4后verify确认已有HAMSTER全局登录可用。`[verified: 本次安装、环境存在性与verify输出]`
- 历史正式目录已封存，软件验证使用独立.local目录。`[verified: 上轮Test-Path test_seal.json返回True；opinion: 验证目录选择]`
- Offline SDK读取url会抛错，适配器按online模式读取URL。Windows诊断改用UTF-8输出。`[verified: 本次sdk-probe异常、修复后probe和UTF-8 ping输出]`
- C1误启动会覆盖跟踪身份，已在创建run前检查检查点／resume及优化配置，并补充身份不变测试。`[verified: review_experiment的C1、复查CLEAN与test_rejected_train_preserves_swanlab_identity]`
- C2默认阶段目录不同，已让五个脚本共享TOML并增加五个默认配置一致性用例。`[verified: review_experiment的C2、复查CLEAN与test_script_stages_share_default_configuration]`

## Questions for review

- 检查默认数值行为、断点恢复、SwanLab身份与步数、失败收尾及离线产物。`[opinion]`

## Summary

记录3项实现与验证选择。`[verified: 本文Deviations]`

最可能调整的是默认SwanLab项目与workspace配置。`[opinion]`

已处理5项依赖、封存、SDK输出及入口身份边界。`[verified: 本文Discovered edge cases]`

独立审查的C1、C2均已修复，复查返回CLEAN。`[verified: 本次review_experiment最终回复]`

后续先读本目录README、verification.json和script/train_config.toml。`[opinion]`
