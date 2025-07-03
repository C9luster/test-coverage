import os
import subprocess
import sys
import time
import concurrent.futures
import re
import uuid
import importlib

def find_test_files(test_dir):
    """查找所有以test_开头的测试文件（.py）"""
    result = []
    for dirpath, dirnames, filenames in os.walk(test_dir):
        for filename in filenames:
            if filename.startswith("test_") and filename.endswith(".py"):
                abs_path = os.path.abspath(os.path.join(dirpath, filename))
                result.append(abs_path)
    return result

def relpath_from_tests(test_file, tests_dir):
    """获取测试文件相对于tests目录的路径"""
    return os.path.relpath(test_file, tests_dir)

def is_serial_test(test_file):
    """判断测试文件是否含有@SerialUnitTest"""
    try:
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()
            # 匹配 @SerialUnitTest 装饰器
            return re.search(r'@SerialUnitTest', content) is not None
    except Exception:
        return False

def is_skip_test(test_file):
    """判断测试文件是否含有@SkipUnitTest"""
    try:
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()
            return '@SkipUnitTest' in content
    except Exception:
        return False

def run_single_test(test_file, coverage_data_file, tests_dir):
    env = os.environ.copy()
    env['COVERAGE_FILE'] = coverage_data_file
    start_time = time.time()
    proc = subprocess.run(
        ["coverage", "run", "--append", test_file],
        capture_output=True, text=True, env=env
    )
    end_time = time.time()
    elapsed = end_time - start_time
    is_fail = proc.returncode != 0 or (proc.stderr and 'FAIL' in proc.stderr)
    rel_path = relpath_from_tests(test_file, tests_dir)
    return {
        "file": test_file,
        "rel_path": rel_path,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
        "elapsed": elapsed,
        "is_fail": is_fail
    }

def parallel_worker(args):
    test_file, coverage_dir, tests_dir = args
    worker_cov_file = os.path.join(coverage_dir, f".coverage.worker-{uuid.uuid4()}")
    res = run_single_test(test_file, worker_cov_file, tests_dir)
    return res, worker_cov_file

def print_test_results(results, max_label_len):
    for res in results:
        time_str = f"{res['elapsed']:.3f}s"
        pad = " " * (max_label_len - len(res["label"]))
        if res["is_fail"]:
            print(f"\033[91m{res['label']}{pad} {time_str:>8}\033[0m")
        else:
            print(f"\033[92m{res['label']}{pad} {time_str:>8}\033[0m")

def print_failed_details(failed_results):
    if failed_results:
        print("\n========== 失败测试详细信息 ==========")
        for res in failed_results:
            attempt_str = f" (第{res['attempt']}次)" if res['attempt'] > 1 else ""
            print(f"\n---------------- \033[91m⚠️ {res['rel_path']}⚠️{attempt_str}\033[0m ----------------")
            if res["stdout"]:
                print(res["stdout"])
            if res["stderr"]:
                print("错误输出：")
                print(res["stderr"])
            print(f"返回码: {res['returncode']}")

def run_parallel_tests(test_files, coverage_dir, tests_dir, coverage_data_file):
    results = []
    labels = []
    args_list = [(test_file, coverage_dir, tests_dir) for test_file in test_files]
    worker_cov_files = []
    import os, time
    t0 = time.time()
    retry_time = 0.0
    # 第1轮
    with concurrent.futures.ProcessPoolExecutor() as executor:
        future_to_file = {executor.submit(parallel_worker, args): args[0] for args in args_list}
        for future in concurrent.futures.as_completed(future_to_file):
            res, cov_file = future.result()
            worker_cov_files.append(cov_file)
            label = f"❌ [FAIL] {res['rel_path']}" if res["is_fail"] else f"✅ [OK]   {res['rel_path']}"
            res["label"] = label
            res["attempt"] = 1
            results.append(res)
            labels.append(label)
    results.sort(key=lambda x: x['rel_path'])
    max_label_len = max(len(l) for l in labels) if labels else 0
    print_test_results(results, max_label_len)
    failed = [r for r in results if r["is_fail"]]
    print_failed_details(failed)
    # 第2、3轮重试
    for round_num in [2, 3]:
        if not failed:
            break
        retry_results = []
        retry_labels = []
        retry_args_list = [(res["file"], coverage_dir, tests_dir) for res in failed]
        t_retry = time.time()
        with concurrent.futures.ProcessPoolExecutor() as executor:
            future_to_file = {executor.submit(parallel_worker, args): args[0] for args in retry_args_list}
            for future in concurrent.futures.as_completed(future_to_file):
                retry_res, cov_file = future.result()
                worker_cov_files.append(cov_file)
                retry_res["label"] = f"❌ [FAIL] {retry_res['rel_path']} (重试{round_num})" if retry_res["is_fail"] else f"✅ [OK]   {retry_res['rel_path']} (重试{round_num})"
                retry_res["attempt"] = round_num
                retry_results.append(retry_res)
                retry_labels.append(retry_res["label"])
        retry_time += time.time() - t_retry
        retry_results.sort(key=lambda x: x['rel_path'])
        retry_max_label_len = max(len(l) for l in retry_labels) if retry_labels else 0
        print(f"\n----------------  第{round_num}轮重新测试  ----------------")
        print_test_results(retry_results, retry_max_label_len)
        failed = [r for r in retry_results if r["is_fail"]]
        print_failed_details(failed)
        results.extend(retry_results)
    # 不要在这里删除 worker_cov_files，交给 main 统一处理
    total_time = time.time() - t0
    return results, total_time, retry_time, worker_cov_files

def run_with_retries(test_files, coverage_data_file, tests_dir, section_name):
    print(f"\n================ {section_name} ================")
    t0 = time.time()
    retry_time = 0.0
    # 第一轮
    results = []
    labels = []
    for test_file in test_files:
        res = run_single_test(test_file, coverage_data_file, tests_dir)
        label = f"❌ [FAIL] {res['rel_path']}" if res["is_fail"] else f"✅ [OK]   {res['rel_path']}"
        labels.append(label)
        res["label"] = label
        res["attempt"] = 1
        results.append(res)
    max_label_len = max(len(l) for l in labels) if labels else 0
    print_test_results(results, max_label_len)
    failed = [r for r in results if r["is_fail"]]
    print_failed_details(failed)

    # 第一轮重试
    if failed:
        retry_results_2 = []
        retry_labels_2 = []
        t_retry2 = time.time()
        for res in failed:
            retry_res = run_single_test(res["file"], coverage_data_file, tests_dir)
            retry_res["label"] = f"❌ [FAIL] {retry_res['rel_path']} (重试2)" if retry_res["is_fail"] else f"✅ [OK]   {retry_res['rel_path']} (重试2)"
            retry_res["attempt"] = 2
            retry_labels_2.append(retry_res["label"])
            retry_results_2.append(retry_res)
        retry_time += time.time() - t_retry2
        retry_max_label_len_2 = max(len(l) for l in retry_labels_2) if retry_labels_2 else 0
        print("\n----------------  第2轮重新测试  ----------------")
        print_test_results(retry_results_2, retry_max_label_len_2)
        failed_2 = [r for r in retry_results_2 if r["is_fail"]]
        print_failed_details(failed_2)
    else:
        retry_results_2 = []
        failed_2 = []

    # 第二轮重试
    if failed_2:
        retry_results_3 = []
        retry_labels_3 = []
        t_retry3 = time.time()
        for res in failed_2:
            retry_res = run_single_test(res["file"], coverage_data_file, tests_dir)
            retry_res["label"] = f"❌ [FAIL] {retry_res['rel_path']} (重试3)" if retry_res["is_fail"] else f"✅ [OK]   {retry_res['rel_path']} (重试3)"
            retry_res["attempt"] = 3
            retry_labels_3.append(retry_res["label"])
            retry_results_3.append(retry_res)
        retry_time += time.time() - t_retry3
        retry_max_label_len_3 = max(len(l) for l in retry_labels_3) if retry_labels_3 else 0
        print("\n----------------  第3轮重新测试  ----------------")
        print_test_results(retry_results_3, retry_max_label_len_3)
        failed_3 = [r for r in retry_results_3 if r["is_fail"]]
        print_failed_details(failed_3)
        all_results = results + retry_results_2 + retry_results_3
    else:
        all_results = results + retry_results_2
    total_time = time.time() - t0
    return all_results, total_time, retry_time

def generate_coverage_report(include_dirs, html_output_dir=None, xml_output_file=None, coverage_data_file=None):
    env = os.environ.copy()
    if coverage_data_file:
        env['COVERAGE_FILE'] = coverage_data_file
    try:
        # 使用绝对路径，防止路径BUG
        agents_dir_abs = os.path.abspath(include_dirs[0])
        utils_dir_abs = os.path.abspath(include_dirs[1])
        include_pattern = f"{agents_dir_abs}/*,{utils_dir_abs}/*"
        # 1. 只统计被测代码
        subprocess.run(["coverage", "report", f"--include={include_pattern}"], check=True, env=env)
        # 2. 生成 html 报告
        if html_output_dir:
            subprocess.run([
                "coverage", "html", f"--include={include_pattern}", "-d", html_output_dir
            ], check=True, env=env)
            print(f"\033[92m✅ 覆盖率报告已生成，HTML报告在{html_output_dir}目录下。\033[0m")
        # 3. 只针对 agents 和 utils 生成 xml
        if xml_output_file:
            subprocess.run([
                "coverage", "xml", f"--include={include_pattern}", "-o", xml_output_file
            ], check=True, env=env)
            print(f"\033[92m✅ XML覆盖率报告已生成，文件名为: {xml_output_file}\033[0m")
    except subprocess.CalledProcessError as e:
        print(f"生成覆盖率报告失败: {e}", file=sys.stderr)

def import_all_modules_from_dir(module_dir, module_prefix):
    for root, dirs, files in os.walk(module_dir):
        for file in files:
            if file.endswith('.py') and file != '__init__.py':
                rel_path = os.path.relpath(os.path.join(root, file), module_dir)
                mod_name = rel_path[:-3].replace(os.sep, '.')
                full_mod_name = f"{module_prefix}.{mod_name}"
                try:
                    importlib.import_module(full_mod_name)
                except Exception as e:
                    print(f"导入模块 {full_mod_name} 失败: {e}")

def main():
    # 获取项目根目录（假设本脚本在tests目录下）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    test_dir = os.path.join(project_root, "tests")
    agents_dir = os.path.join(project_root, "agents")
    utils_dir = os.path.join(project_root, "utils")
    htmlcov_dir = os.path.join(test_dir, "htmlcov")
    coverage_result_dir = os.path.join(test_dir, "coverage_result")
    coverage_data_file = os.path.join(test_dir, ".coverage")
    coverage_xml_file = os.path.join(test_dir, "coverage.xml")

    # 在测试前 import 所有被测模块，确保 coverage 能检测到
    import_all_modules_from_dir(agents_dir, 'test_coverage.agents')
    import_all_modules_from_dir(utils_dir, 'test_coverage.utils')

    # 检查目录是否存在
    for d in [test_dir, agents_dir, utils_dir]:
        if not os.path.isdir(d):
            print(f"目录不存在: {d}", file=sys.stderr)
            return

    # 创建结果目录
    os.makedirs(htmlcov_dir, exist_ok=True)
    os.makedirs(coverage_result_dir, exist_ok=True)

    # 清理 coverage_result_dir 下所有 .coverage* 文件
    for f in os.listdir(test_dir):
        if f.startswith('.coverage'):
            try:
                os.remove(os.path.join(test_dir, f))
            except Exception:
                pass

    # 查找测试文件
    test_files = find_test_files(test_dir)
    if not test_files:
        print("未找到任何测试文件。", file=sys.stderr)
        return

    # 清理旧的coverage数据
    env = os.environ.copy()
    env['COVERAGE_FILE'] = coverage_data_file
    subprocess.run(["coverage", "erase"], env=env)

    # 分类：skip/serial/parallel
    skip_files = []
    serial_files = []
    parallel_files = []
    for f in test_files:
        if is_skip_test(f):
            skip_files.append(f)
        elif is_serial_test(f):
            serial_files.append(f)
        else:
            parallel_files.append(f)

    # 跳过的测试文件
    if skip_files:
        print("\n================ 跳过的测试 ================")
        for f in skip_files:
            rel_path = relpath_from_tests(f, test_dir)
            print(f"⏭️  跳过: {rel_path}")

    total_parallel_time = 0.0
    total_serial_time = 0.0
    total_retry_time = 0.0

    # 并行和串行分别用不同的 coverage 文件
    # 并行测试不传 coverage_data_file，让 worker 只生成 .coverage.worker-xxxx
    coverage_data_file_serial = os.path.join(test_dir, ".coverage.serial")

    all_worker_cov_files = []
    # 并行测试
    if parallel_files:
        print("\n================ 并行测试 ================")
        _, parallel_time, parallel_retry_time, worker_cov_files = run_parallel_tests(parallel_files, test_dir, test_dir, None)
        all_worker_cov_files.extend(worker_cov_files)
        total_parallel_time += parallel_time
        total_retry_time += parallel_retry_time
    # 串行测试
    if serial_files:
        _, serial_time, serial_retry_time = run_with_retries(serial_files, coverage_data_file_serial, test_dir, section_name="串行测试")
        total_serial_time += serial_time
        total_retry_time += serial_retry_time

    total_time = total_parallel_time + total_serial_time
    print("\n================ 测试时间统计 ================")
    print(f"并行测试耗时: {total_parallel_time:.3f}s")
    print(f"串行测试耗时: {total_serial_time:.3f}s")
    print(f"总耗时:       {total_time:.3f}s")

    # 合并所有 .coverage* 文件，确保覆盖率完整
    subprocess.run(["coverage", "combine"], check=True, env=env)

    # 合并后统一删除所有 .coverage.worker-* 文件
    for f in all_worker_cov_files:
        try:
            os.remove(f)
        except Exception:
            pass

    # 生成html报告和xml报告，全部放在tests/coverage_result和tests/htmlcov下
    generate_coverage_report(
        [agents_dir, utils_dir],
        html_output_dir=htmlcov_dir,
        xml_output_file=coverage_xml_file,
        coverage_data_file=coverage_data_file
    )

if __name__ == "__main__":
    main()