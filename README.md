# 介绍

简单的HTTP跳板，不支持WS（可能吧，没试过），适用于非延迟敏感类型服务

# 如何使用

将 `server.py` 部署在公网服务器上并运行，在 `client.py` 设置
服务端地址，链接成功即可使用。

请自行配置反代

# 延迟表现

在服务器直链延迟 `160~200ms` 的情况下，平均 `1.6~2.3s` 的
延迟，瞬时最快 `200ms`
