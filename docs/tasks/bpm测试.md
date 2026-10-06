# bpm 测试

现在bpm 可以任意组合，从业务角度来说，并非所有组合都是合法的。
我们希望用户使用默认流程，但是真实需求是用户需求千奇百怪。
我们用如下步骤定义流程节点

- 上传PDF(Upload)
- PDF提取（Extract）
- 文本框识别（Detect）
- 去底色（Rembg）
- 拼版（Imposition）
- 生成PDF(Print)

## 以下是可能的流程组合

1. upload -> extract -> detect -> rembg ->(imposition) -> print
2. detect -> rembg ->(imposition) -> print
3. rembg -> (imposition) -> print
4. impositon -> print
5. print
6. extract
7. detect
8. rembg
9. imposition
10. (detect, rembg, impositon 任意顺序任意个数)(print) 相互组合，但是print如果有就放在最后

上述10条如果有问题自己验证

其他的认定不合法，比如
print -> rembg

## 特殊

upload extract 一般一起存在
impositon 和 gateway 节点一般同时同在

这两种情况在 bpmn 编辑的时候有体现

## 测试

拿真实数据测试 （~/Downloads/ 下的文件）尽可能测试合法流程，有问题修复
不合法的流程，创建或者编辑保存的时候，就判断出来不合法，拒绝保存

我的想法可能有问题，但是你自己测试解决问题
