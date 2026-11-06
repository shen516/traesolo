"""训练域拆分。

- hyperparam / walkforward：网格搜索与 walk-forward 评估
- executor：样本筛选、ELO/泊松/xG、落库、融合训练主流程
- smoothing：权重 EMA / 小样本向全局收缩

对外仍经 `services.training_service.training_service` 门面调用。
"""
