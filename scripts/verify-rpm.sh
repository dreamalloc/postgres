#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 产物校验（PostgreSQL 版）
#   TARGET_NAME  目标平台名（打印用）
#   GLIBC_MAX    glibc 符号版本上限
#   EXPECT_ARCH  期望架构
#   ARCH_HINT    file 命令输出的架构关键字
# ---------------------------------------------------------------------------
set -eu
if [ -n "${BASH_VERSION:-}" ]; then set +o pipefail; fi

TOP="${RPMBUILD_TOP:-/build/rpmbuild}"
TARGET_NAME="${TARGET_NAME:-Kylin V10 SP3 (aarch64)}"
GLIBC_MAX="${GLIBC_MAX:-2.28}"
EXPECT_ARCH="${EXPECT_ARCH:-aarch64}"
ARCH_HINT="${ARCH_HINT:-ARM aarch64}"
PGMAJOR="${PGMAJOR:-13}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cd "$TOP"

echo "======================= 产物清单 ======================="
printf '%-66s %-10s %6s\n' FILE ARCH SIZE
find RPMS -name '*.rpm' | sort | while read -r f; do
    printf '%-66s %-10s %6s\n' "$(basename "$f")" "$(rpm -qp --qf '%{ARCH}' "$f" 2>/dev/null)" "$(du -h "$f" | cut -f1)"
done

RPMS="$(find RPMS -name '*.rpm' -not -name '*.src.rpm')"

echo
echo "=================== 1. 架构一致性 ====================="
ARCHS="$(for f in $RPMS; do rpm -qp --qf '%{ARCH}\n' "$f" 2>/dev/null; done | sort -u | grep -v '^$' | tr '\n' ' ')"
echo "    架构集合: $ARCHS"
if echo "$ARCHS" | tr ' ' '\n' | grep -v '^$' | grep -qv "^${EXPECT_ARCH}$"; then
    echo "!! 存在非 ${EXPECT_ARCH} 产物"; exit 1
fi

echo
echo "=================== 2. debuginfo ======================"
DBG="$(find RPMS -name '*server-debuginfo-*.rpm' | sort | sed -n '1p' || true)"
if [ -z "$DBG" ]; then
    DBG="$(find RPMS -name '*-debuginfo-*.rpm' | grep -v debugsource | sort | sed -n '1p' || true)"
fi
DBG_ALL="$(find RPMS -name '*-debuginfo-*.rpm' | wc -l)"
if [ -n "$DBG" ]; then
    echo "    debuginfo 包 ${DBG_ALL} 个，代表: $(basename "$DBG") ($(du -h "$DBG" | cut -f1))"
    echo "    其中 .debug 文件 $(rpm -qlp "$DBG" | grep -c '\.debug$') 个"
else
    echo "    debuginfo: 未生成（可接受，但符号无法回溯）"
fi

echo
echo "=================== 3. glibc 符号版本 ================="
MAXV=""
for f in $RPMS; do
    v="$(rpm -qpR "$f" 2>/dev/null | grep -o 'GLIBC_[0-9][0-9.]*' | sed 's/GLIBC_//' | sort -Vu | tail -1 || true)"
    [ -z "$v" ] && continue
    if [ -z "$MAXV" ] || [ "$(printf '%s\n%s\n' "$MAXV" "$v" | sort -V | tail -1)" = "$v" ]; then
        MAXV="$v"
    fi
done
echo "    最高依赖符号版本: ${MAXV:-未知}  (目标平台 ${TARGET_NAME} 上限 ${GLIBC_MAX})"
if [ -n "$MAXV" ] && [ "$(printf '%s\n%s\n' "$MAXV" "$GLIBC_MAX" | sort -V | tail -1)" != "$GLIBC_MAX" ]; then
    echo "!! 产物依赖 GLIBC_${MAXV}，高于 ${TARGET_NAME} 的 ${GLIBC_MAX}，装不上"
    exit 1
fi

echo
echo "=================== 4. systemd 单元 ==================="
SRV="$TOP/$(find RPMS -name '*-server-*.rpm' -not -name '*debug*' -not -name '*.src.rpm' | sed -n '1p')"
[ -n "$SRV" ] && [ "$SRV" != "$TOP/" ] || { echo "!! 找不到 server 主包"; exit 1; }
mkdir -p "$WORK/u"
( cd "$WORK" && rpm2cpio "$SRV" | cpio -idm --quiet 2>/dev/null ) || true
UNIT="$WORK/usr/lib/systemd/system/postgresql-${PGMAJOR}.service"
if [ -f "$UNIT" ]; then
    echo "    --- postgresql-${PGMAJOR}.service ---"
    grep -E '^(Type|User|Group|Environment|ExecStart|ExecStartPre|ExecReload)=' "$UNIT" | sed 's/^/        /'
else
    echo "!! 单元文件缺失: postgresql-${PGMAJOR}.service"; exit 1
fi
grep -q "postgresql-${PGMAJOR}-initdb" "$UNIT" \
    || { echo "!! 单元未引用 postgresql-${PGMAJOR}-initdb，首启不会自动 initdb"; exit 1; }
[ -f "$WORK/usr/bin/postgresql-${PGMAJOR}-initdb" ] \
    || { echo "!! 缺少 /usr/bin/postgresql-${PGMAJOR}-initdb"; exit 1; }

echo "    systemd-analyze verify:"
systemd-analyze verify "$UNIT" 2>&1 | sed 's/^/        /' || true

echo
echo "=================== 5. 二进制 ELF 架构 ================"
file "$WORK/usr/bin/postgres" | sed 's/^/    /'
file "$WORK/usr/bin/postgres" | grep -q "${ARCH_HINT}" \
    || { echo "!! postgres 不是 ${EXPECT_ARCH} ELF"; exit 1; }

echo
echo "=================== 6. 版本自证 ======================="
if [ -x "$WORK/usr/bin/pg_config" ]; then
    echo "    pg_config --version: $(LD_LIBRARY_PATH="$WORK/usr/lib64" "$WORK/usr/bin/pg_config" --version 2>/dev/null || echo '无法在本机执行')"
fi

echo
echo "=================== 7. 生成校验和与构建信息 ==========="
( cd "$TOP" && find RPMS SRPMS -name '*.rpm' | sort | xargs sha256sum > SHA256SUMS )
sed 's/^/    /' SHA256SUMS | sed -n '1,20p'

{
    echo "PostgreSQL ${SRC_NAME#postgresql-} RPM build for ${TARGET_NAME}"
    echo "=============================================================="
    echo "build time   : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "source repo  : dreamalloc/postgres"
    echo "source ref   : ${SRC_REF:-REL_13_23}"
    echo "source commit: $(cat /tmp/src_commit.txt 2>/dev/null || echo unknown)"
    echo "runner       : ${EXPECT_ARCH} / $(nproc) vCPU"
    echo "build rootfs : $(cat /etc/redhat-release 2>/dev/null || cat /etc/openEuler-release 2>/dev/null || echo unknown)"
    echo "gcc          : $(gcc --version | sed -n '1p')"
    echo "glibc        : $(ldd --version | sed -n '1p')"
    echo
    echo "Install on ${TARGET_NAME}"
    echo "----------------------------------"
    echo "  tar xf postgresql13-13.23-*.tar.gz"
    echo "  dnf install ./*.rpm            # 或 rpm -Uvh ./*.rpm"
    echo "  systemctl enable --now postgresql-13  # 首次启动自动 initdb"
    echo "  su - postgres -c 'psql'         # peer 认证，本地免密"
} > BUILD-INFO.txt
cat BUILD-INFO.txt | sed 's/^/    /'
