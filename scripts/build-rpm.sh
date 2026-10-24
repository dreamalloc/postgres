#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# PostgreSQL 13.23 → RPM（与 MySQL 那套流程同构，去掉 Boost 相关逻辑）
#
# 入参（环境变量）：
#   SRC_DIR        PostgreSQL 源码目录（必需）
#   SRC_NAME       源码顶层目录名，默认 postgresql-13.23
#   SPEC_FILE      spec 文件名，默认 postgresql13.spec
#   DIST_TAG       Release 后缀，默认 .ky10
#   RPMBUILD_TOP   rpmbuild 顶层目录，默认 /build/rpmbuild
#   BUILD_FLAVOR   额外 rpm 宏（可选，如 oe2403）
#   ALLOW_UNPACKAGED 1 = 容忍未打包文件（调试用）
# ---------------------------------------------------------------------------
set -eu
if [ -n "${BASH_VERSION:-}" ]; then set +o pipefail; fi

SRC_DIR="${SRC_DIR:?需要指定 SRC_DIR（PostgreSQL 源码路径）}"
SRC_NAME="${SRC_NAME:-postgresql-13.23}"
DIST_TAG="${DIST_TAG:-.ky10}"
TOP="${RPMBUILD_TOP:-/build/rpmbuild}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC_FILE="${SPEC_FILE:-postgresql13.spec}"
SPEC="${REPO_ROOT}/packaging/rpm/${SPEC_FILE}"
SPEC_NAME="$(basename "${SPEC}")"

[ -d "$SRC_DIR" ]  || { echo "!! 源码目录不存在: $SRC_DIR"; exit 1; }
[ -f "$SPEC" ]     || { echo "!! 找不到 spec: $SPEC"; exit 1; }

echo "==> 清理并准备 rpmbuild 目录"
for d in BUILD BUILDROOT RPMS SOURCES SPECS SRPMS; do
    rm -rf "${TOP:?}/$d"
    mkdir -p "$TOP/$d"
done

echo "==> 打包源码（顶层目录 ${SRC_NAME}/）"
# PG 的 configure 已随源码提供，不需要 autoconf
tar -C "$(dirname "$SRC_DIR")" -czf "${TOP}/SOURCES/${SRC_NAME}.tar.gz" \
    --transform "s,^$(basename "$SRC_DIR"),${SRC_NAME}," \
    "$(basename "$SRC_DIR")"
ls -lh "${TOP}/SOURCES/${SRC_NAME}.tar.gz" | awk '{print "    "$5}'

cp -f "$SPEC" "${TOP}/SPECS/${SPEC_NAME}"

echo "==> 校验 spec 可解析"
rpmspec -q --qf '    %{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' "${TOP}/SPECS/${SPEC_NAME}"

JOBS="$(nproc)"
echo "==> rpmbuild -ba  (dist=${DIST_TAG}, -j${JOBS})"

set -- -ba "${TOP}/SPECS/${SPEC_NAME}" \
    --define "_topdir ${TOP}" \
    --define "dist ${DIST_TAG}" \
    --define "_smp_mflags -j${JOBS}"

if [ -n "${BUILD_FLAVOR:-}" ]; then
    set -- "$@" --define "${BUILD_FLAVOR} 1"
    echo "    (flavor: ${BUILD_FLAVOR})"
fi

if [ "${ALLOW_UNPACKAGED:-0}" = "1" ]; then
    echo "    [调试模式] 容忍未打包文件（产物不完整，禁止发布）"
    set -- "$@" --define "_unpackaged_files_terminate_build 0"
fi

set +e
rpmbuild "$@" > "${TOP}/build.log" 2>&1
RC=$?
set -e

if [ "$RC" -ne 0 ]; then
    echo
    echo "=========================================================="
    echo " 构建失败。常见原因：%files 与实际安装文件不一致"
    echo "=========================================================="
    sed -n '/Installed (but unpackaged) file(s) found/,/^$/p' "${TOP}/build.log" | sed -n '1,100p'
    echo
    echo "完整 buildroot 清单见: ${TOP}/BUILD/${SRC_NAME}/buildroot-files.txt"
    echo "完整日志: ${TOP}/build.log"
    exit "$RC"
fi

echo
echo "==> 构建成功，产物："
find "${TOP}/RPMS" "${TOP}/SRPMS" -name '*.rpm' | sort | while read -r f; do
    printf '    %-70s %8s\n' "$(basename "$f")" "$(du -h "$f" | cut -f1)"
done
