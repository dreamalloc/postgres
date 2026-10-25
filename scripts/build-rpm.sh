#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# PostgreSQL 13.23 → RPM（与 MySQL 那套流程同构，去掉 Boost 相关逻辑）
#
# 入参（环境变量）：
#   SRC_TARBALL    官方源码包路径（优先；PGDG 布局需要 tarball 里的预生成 man）
#   SRC_DIR        PostgreSQL 源码目录（SRC_TARBALL 未提供时的回退）
#   SRC_NAME       源码顶层目录名，默认 postgresql-13.23
#   SPEC_FILE      spec 文件名，默认 postgresql13.spec
#   DIST_TAG       Release 后缀，默认 .ky10
#   RPMBUILD_TOP   rpmbuild 顶层目录，默认 /build/rpmbuild
#   BUILD_FLAVOR   额外 rpm 宏（可选，如 oe2403）
#   ALLOW_UNPACKAGED 1 = 容忍未打包文件（调试用）
# ---------------------------------------------------------------------------
set -eu
if [ -n "${BASH_VERSION:-}" ]; then set +o pipefail; fi

SRC_TARBALL="${SRC_TARBALL:-}"
SRC_DIR="${SRC_DIR:-}"
SRC_NAME="${SRC_NAME:-postgresql-13.23}"
DIST_TAG="${DIST_TAG:-.ky10}"
TOP="${RPMBUILD_TOP:-/build/rpmbuild}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_TARBALL_NAME="${SRC_TARBALL_NAME:-${SRC_NAME}.tar.gz}"
SPEC_FILE="${SPEC_FILE:-postgresql.spec}"
SPEC="${REPO_ROOT}/packaging/rpm/${SPEC_FILE}"
SPEC_NAME="$(basename "${SPEC}")"

if [ -n "${SRC_TARBALL}" ]; then
    [ -s "$SRC_TARBALL" ] || { echo "!! 源码包不存在或为空: $SRC_TARBALL"; exit 1; }
elif [ -n "${SRC_DIR}" ]; then
    [ -d "$SRC_DIR" ] || { echo "!! 源码目录不存在: $SRC_DIR"; exit 1; }
else
    echo "!! 需要 SRC_TARBALL 或 SRC_DIR"; exit 1
fi
[ -f "$SPEC" ]     || { echo "!! 找不到 spec: $SPEC"; exit 1; }

echo "==> 清理并准备 rpmbuild 目录"
for d in BUILD BUILDROOT RPMS SOURCES SPECS SRPMS; do
    rm -rf "${TOP:?}/$d"
    mkdir -p "$TOP/$d"
done

echo "==> 准备源码"
if [ -n "${SRC_TARBALL}" ] && [ -s "${SRC_TARBALL}" ]; then
    # 官方 release tarball：顶层目录已是 postgresql-<ver>，且含预生成 man 页
    cp -f "${SRC_TARBALL}" "${TOP}/SOURCES/${SRC_TARBALL_NAME}"
    echo "    使用官方 tarball: ${SRC_TARBALL_NAME}"
elif [ -n "${SRC_DIR}" ] && [ -d "${SRC_DIR}" ]; then
    echo "    回退：从源码目录重新打包（无 man 页）"
    tar -C "$(dirname "$SRC_DIR")" -czf "${TOP}/SOURCES/${SRC_TARBALL_NAME}" \
        --transform "s,^$(basename "$SRC_DIR"),${SRC_NAME}," \
        "$(basename "$SRC_DIR")"
else
    echo "!! 既没有 SRC_TARBALL 也没有 SRC_DIR"; exit 1
fi
ls -lh "${TOP}/SOURCES/${SRC_TARBALL_NAME}" | awk '{print "    "$5}'

# 附带源码：systemd 单元模板（官方 PGDG 单元）
SERVICE_TPL="${REPO_ROOT}/packaging/rpm/postgresql.service.in"
[ -f "$SERVICE_TPL" ] || { echo "!! 找不到单元模板: $SERVICE_TPL"; exit 1; }
cp -f "$SERVICE_TPL" "${TOP}/SOURCES/postgresql.service.in"

cp -f "$SPEC" "${TOP}/SPECS/${SPEC_NAME}"

echo "==> 校验 spec 可解析"
SPEC_DEFS=(--define "_topdir ${TOP}" --define "dist ${DIST_TAG}")
[ -n "${PGMAJOR:-}" ]   && SPEC_DEFS+=(--define "pgmajor ${PGMAJOR}")
[ -n "${PGVERSION:-}" ] && SPEC_DEFS+=(--define "pgversion ${PGVERSION}")
[ -n "${BUILD_FLAVOR:-}" ] && SPEC_DEFS+=(--define "${BUILD_FLAVOR} 1")
if ! rpmspec -q --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' \
        "${SPEC_DEFS[@]}" "${TOP}/SPECS/${SPEC_NAME}" > "${TOP}/spec-check.out" 2>&1; then
    echo "!! spec 解析失败:"
    sed 's/^/    /' "${TOP}/spec-check.out"
    cp -f "${TOP}/spec-check.out" "${TOP}/build.log"
    exit 1
fi
sed 's/^/    /' "${TOP}/spec-check.out"

JOBS="$(nproc)"
echo "==> rpmbuild -ba  (dist=${DIST_TAG}, -j${JOBS})"

set -- -ba "${TOP}/SPECS/${SPEC_NAME}" \
    --define "_topdir ${TOP}" \
    --define "dist ${DIST_TAG}" \
    --define "_smp_mflags -j${JOBS}"

if [ -n "${PGMAJOR:-}" ]; then
    set -- "$@" --define "pgmajor ${PGMAJOR}"
    echo "    (pgmajor: ${PGMAJOR})"
fi
if [ -n "${PGVERSION:-}" ]; then
    set -- "$@" --define "pgversion ${PGVERSION}"
fi
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
    echo "--- File not found ---"
    grep -E "File not found" "${TOP}/build.log" | sed -n '1,60p' || true
    echo
    echo "--- Installed (but unpackaged) ---"
    sed -n '/Installed (but unpackaged)/,/^\s*$/p' "${TOP}/build.log" | sed -n '1,120p'
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
