# Class-based module refactor

## Deviations

- 核心工作流使用独立class，旧函数路径保留薄兼容入口，供既有实验脚本继续调用。`[opinion]`
- ASTCClassifier直接继承torchvision ResNet，保持原生state_dict参数名及初始化顺序。`[verified: 已安装torchvision.models.resnet的resnet18与_resnet源码]`
- 多文件实现的来源记录增加source_files_sha256，保留原source_code_sha256字段。`[verified: training/trainer.py的config构建]`

## Discovered edge cases

- prepare需要保持CPU依赖路径，data包导入时延迟加载torch Dataset。`[verified: 重构前cli.py L11、L64-L66的导入位置]`
- 历史数据测试封存已完成，回归检查使用独立私有目录并记录旧工件哈希。`[opinion]`
- Trainer清理模型时同步释放scheduler引用，防止保留optimizer和参数。`[verified: training/trainer.py的fit末尾del语句]`
- 旧脚本对data.SNAPSHOT_SHA256的测试注入通过兼容入口传递，class API同时支持显式expected_sha256。`[verified: data/__init__.py的catalog、prepare；TextureCatalog和DataPreparer构造函数]`

## Questions for review

- 核对初始化、训练与恢复、校准、测试封存及旧导入入口的兼容性。`[opinion]`

## Summary

兼容与溯源选择共3项。`[verified: 本文Deviations三条记录]`

后续最可能调整的是旧函数兼容入口的保留周期。`[opinion]`

已记录4项依赖、封存、资源释放和测试注入边界。`[verified: 本文Discovered edge cases四条记录]`

独立审查返回CLEAN，数值与CLI检查记录在verification.json。`[verified: 本次review_experiment返回；verification.json的status]`

下次先阅读本目录README和verification.json，再修改对应职责class。`[opinion]`
