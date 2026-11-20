# 滨岬双头测厚站

滨岬材料试验室的白班主管冻结当天清册和定标。台架工逐片固定装夹，采集员接管异步回包，质检员签发测厚差值，夜班关掉设备后仍可领取原码和判级。

## 运行

需要 Python 3.11 标准库。以下命令从项目根目录执行。

```sh
python3 -B check_project.py
python3 -B -m unittest discover -s tests -t .
python3 -B -m station
```

`check_project.py` 由运行平台提供。演示在临时目录建立站库，用固定顺序驱动物理事件和乱序回包，关闭源与站库后重开领取。输出的 `POINTWISE_SCENARIO` 行包含手算预期、实测结果和离线领件。发生业务断言或运行错误时命令以非零状态退出。初始化只建立结构，重开保留已登记班次、原件、确认待办和已签结果。

## 当班作业

1. 主管通过 `Station(path).shifts.open(shift_id, specimens, left, right, tolerance)` 冻结班次。清册是非空有序序列，片号唯一。`left`、`right` 各是整数倍率与偏移组成的二元序列，容差为非负整数微米。班次与片号是非空文本，按原样比较。`shifts.get(shift_id)` 读取冻结内容，完全相同的开班请求复领原回执。
2. 创建 `OfflineBench(station.shifts)`，通过 `bench.emit('mount', shift_id=..., specimen_id=...)` 装片。占座或未知试片时原装夹保持有效。
3. `bench.request_measurement('left')` 或 `'right'` 返回曝光号。以 `bench.emit('open', exposure_id=..., head=...)` 和 `bench.emit('close', exposure_id=..., head=...)` 交付边沿。`BenchEvent` 也可交给 `bench.apply(event)`，位置从 1 起，每次接受推进一位。发令和回包使用独立入口。已发令或正在曝光时不得卸片，双头闭光后可用 `bench.emit('unmount')` 释放座位，即使原包尚未交付。每班每片每头至多发令一次。再次装入同片时，原固定测量及成果继续有效。
4. `bench.record(exposure_id, raw_code)` 在闭光后登记原包，`bench.deliver_reply(exposure_id)` 可按任意顺序读取尚未回收的包。`capture = station.attach(bench)` 绑定源，`capture.admit(reply)` 按曝光核对班次、试片、头位和整数原码，接管成功才确认设备。设备确认可立即回收该包及其曝光明细。
5. 源确认或本地确认登记失败时，已接管原件仍可用于签发。可重投原包，也可用 `capture.acknowledgements.confirm_exposure(exposure_id)` 或 `retry_pending()` 续办。单件确认返回是否处理了待办。批量续办按曝光号处理，遇到失败即抛出，未完成项保持待办。确认应答丢失后，仍在线的同一设备可识别已回收曝光。
6. `station.quality.issue(shift_id, specimen_id)` 在欠齐时返回 `HeadCoverage`，逐头状态为 `missing` 或 `ready`。齐备时返回 `IssuedResult`。每头的微米值是本班冻结倍率乘原码再加偏移。有符号差是右减左，绝对差小于或等于容差即合格。左右定标为 3x+1 和 2x−2 时，原码 3、7 得到 10、12 μm 和合格差值 2 μm。原码 4、6 得到 13、10 μm 和超差差值 −3 μm。换算和持久存储均保留精确整数。
7. `station.handover.collect(shift_id)` 返回按清册顺序投影的已签账。`station.lookup.collect(number)` 返回指定签件和两条实际原据。尚无已签件的已开班次返回空账。成功签发重投返回原件号，值和原据固定。
8. 调用 `bench.close()` 和 `station.close()`，再打开 `Station(path)`。按号仍可领取原曝光号、测头和原码。

输入或状态冲突用 `ValueError` 报告，未知班次、试片、曝光或成果用 `KeyError` 报告。原码和定标参数使用严格的 Python `int`，布尔值和浮点数拒绝。SQLite 写入错误向调用者传播。领件时发现出处损坏会抛出 `EvidenceError`。每个在线台架由一个调用者顺序驱动物理事件和源确认。可用独立站库连接读取已提交状态。离线台架默认生成设备命名空间，确定性样例显式指定命名空间，使用显式命名空间时应保证同一站库内各台架实例的命名空间唯一。

测试使用真实临时 SQLite 站库和可回收的离线台架。可选失败注入通过 `FaultSchedule.arm(point)` 启用一次故障。常用位置为 `admit.before_commit`、`source.before_confirm`、`source.after_reclaim`、`ack.before_commit`、`issue.after_result` 和 `issue.before_commit`。`Station` 的 `checkpoint` 接收站库回调，`OfflineBench` 的 `checkpoint` 接收源端回调。未安装回调时按正常业务运行。
