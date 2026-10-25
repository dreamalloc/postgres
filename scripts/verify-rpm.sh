#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 产物校验（PostgreSQL PGDG 布局版）
#   TARGET_NAME  目标平台名（打印用）
#   GLIBC_MAX    glibc 符号版本上限
#   EXPECT_ARCH  期望架构
#   ARCH_HINT    file 命令输出的架构关键字
#   PGMAJOR      大版本号（13/15），决定前缀 /usr/pgsql-XX 与单元名
# ---------------------------------------------------------------------------
set -eu
if [ -n "${BASH_VERSION:-}" ]; then set +o pipefail; fi

TOP="${RPMBUILD_TOP:-/build/rpmbuild}"
TARGET_NAME="${TARGET_NAME:-Kylin V10 SP3 (aarch64)}"
GLIBC_MAX="${GLIBC_MAX:-2.28}"
EXPECT_ARCH="${EXPECT_ARCH:-aarch64}"
ARCH_HINT="${ARCH_HINT:-ARM aarch64}"
PGMAJOR="${PGMAJOR:-13}"
PGVERSION="${PGVERSION:-${PGMAJOR}}"
PREFIX="/usr/pgsql-${PGMAJOR}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cd "$TOP"

echo "======================= 产物清单 ======================="
printf '%-72s %-10s %6s\n' FILE ARCH SIZE
find RPMS -name '*.rpm' | sort | while read -r f; do
    printf '%-72s %-10s %6s\n' "$(basename "$f")" "$(rpm -qp --qf '%{ARCH}' "$f" 2>/dev/null)" "$(du -h "$f" | cut -f1)"
done

RPMS="$(find RPMS -name '*.rpm' -not -name '*.src.rpm')"

echo
echo "=================== 1. 架构一致性 ====================="
# docs 子包是 noarch，参与检查会误报；只校验二进制包
# 注意：不能对整个集合串用 grep -qv 判断——串尾空格经 tr 会产生空行，空行会被
# -qv 判成“存在非目标架构”，这里改为逐词比对。
ARCHS="$(for f in $RPMS; do a="$(rpm -qp --qf '%{ARCH}' "$f" 2>/dev/null)"; [ "$a" = "noarch" ] && continue; echo "$a"; done | sort -u | tr '\n' ' ')"
echo "    二进制包架构集合: $ARCHS  (noarch: $(find RPMS -name '*noarch.rpm' -not -name '*.src.rpm' | wc -l) 个)"
for a in $ARCHS; do
    if [ "$a" != "$EXPECT_ARCH" ]; then
        echo "!! 存在非 ${EXPECT_ARCH} 产物: $a"; exit 1
    fi
done

echo
echo "=================== 2. 子包完整性 ====================="
MISSING=""
for sub in libs server contrib devel plperl plpython3 pltcl; do
    if ! find RPMS -name "postgresql${PGMAJOR}-${sub}-*.rpm" -not -name '*debug*' | grep -q .; then
        MISSING="$MISSING $sub"
    fi
done
if [ -n "$MISSING" ]; then
    echo "!! 缺少子包:$MISSING"; exit 1
fi
echo "    子包齐全: libs server contrib devel plperl plpython3 pltcl"

echo
echo "=================== 3. debuginfo / debugsource ========"
DBG_ALL="$(find RPMS -name '*-debuginfo-*.rpm' | wc -l)"
DSRC_ALL="$(find RPMS -name '*-debugsource-*.rpm' | wc -l)"
if [ "${DBG_ALL}" -lt 1 ]; then
    echo "!! 未生成任何 debuginfo 包（with_debug 是否被置为 0？）"; exit 1
fi
DBG="$(find RPMS -name '*server-debuginfo-*.rpm' | sort | sed -n '1p' || true)"
[ -z "$DBG" ] && DBG="$(find RPMS -name '*-debuginfo-*.rpm' | sort | sed -n '1p')"
echo "    debuginfo 包 ${DBG_ALL} 个 / debugsource 包 ${DSRC_ALL} 个"
echo "    代表: $(basename "$DBG") ($(du -h "$DBG" | cut -f1))，.debug 文件 $(rpm -qlp "$DBG" | grep -c '\.debug$') 个"
if [ "${DSRC_ALL}" -ge 1 ]; then
    DSRC="$(find RPMS -name '*-debugsource-*.rpm' | sort | sed -n '1p')"
    echo "    代表: $(basename "$DSRC") ($(du -h "$DSRC" | cut -f1))，源文件 $(rpm -qlp "$DSRC" | grep -cE '\.(c|h|y|l)$') 个"
else
    echo "    !! 未生成 debugsource：检查 optflags 是否含 -g、有无 -fdebug-prefix-map"
fi

echo
echo "=================== 4. glibc 符号版本 ================="
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
echo "=================== 5. systemd 单元 ==================="
SRV="$TOP/$(find RPMS -name '*-server-*.rpm' -not -name '*debug*' -not -name '*.src.rpm' | sed -n '1p')"
[ -n "$SRV" ] && [ "$SRV" != "$TOP/" ] || { echo "!! 找不到 server 主包"; exit 1; }
MAIN="$TOP/$(find RPMS -name "postgresql${PGMAJOR}-${PGVERSION}-*.rpm" -not -name '*debug*' -not -name '*.src.rpm' | sed -n '1p')"
[ -n "$MAIN" ] && [ "$MAIN" != "$TOP/" ] || { echo "!! 找不到 main 客户端包"; exit 1; }
LIBS="$TOP/$(find RPMS -name "postgresql${PGMAJOR}-libs-*.rpm" -not -name '*debug*' -not -name '*.src.rpm' | sed -n '1p')"
[ -n "$LIBS" ] && [ "$LIBS" != "$TOP/" ] || { echo "!! 找不到 libs 包"; exit 1; }
mkdir -p "$WORK"
( cd "$WORK" && rpm2cpio "$SRV"  | cpio -idm --quiet 2>/dev/null ) || true
( cd "$WORK" && rpm2cpio "$MAIN" | cpio -idm --quiet 2>/dev/null ) || true
( cd "$WORK" && rpm2cpio "$LIBS" | cpio -idm --quiet 2>/dev/null ) || true
UNIT="$WORK/usr/lib/systemd/system/postgresql-${PGMAJOR}.service"
if [ -f "$UNIT" ]; then
    echo "    --- postgresql-${PGMAJOR}.service ---"
    grep -E '^(Type|User|Group|Environment|ExecStart|ExecStartPre|ExecReload)=' "$UNIT" | sed 's/^/        /'
else
    echo "!! 单元文件缺失: postgresql-${PGMAJOR}.service"; exit 1
fi
grep -q "postgresql-${PGMAJOR}-check-db-dir" "$UNIT" \
    || { echo "!! 单元未引用 postgresql-${PGMAJOR}-check-db-dir，首启校验缺失"; exit 1; }
grep -q 'Type=notify' "$UNIT" \
    || { echo "!! 单元不是 Type=notify，systemd 无法跟踪 postmaster 就绪"; exit 1; }
[ -f "$WORK${PREFIX}/bin/postgresql-${PGMAJOR}-setup" ] \
    || { echo "!! 缺少 ${PREFIX}/bin/postgresql-${PGMAJOR}-setup"; exit 1; }
[ -f "$WORK${PREFIX}/bin/postgresql-${PGMAJOR}-check-db-dir" ] \
    || { echo "!! 缺少 ${PREFIX}/bin/postgresql-${PGMAJOR}-check-db-dir"; exit 1; }
[ -L "$WORK/usr/bin/postgresql-${PGMAJOR}-setup" ] \
    || { echo "!! 缺少 /usr/bin/postgresql-${PGMAJOR}-setup 软链"; exit 1; }

echo "    systemd-analyze verify:"
systemd-analyze verify "$UNIT" 2>&1 | sed 's/^/        /' || true

echo
echo "=================== 6. 二进制 ELF 架构 ================"
file "$WORK${PREFIX}/bin/postgres" | sed 's/^/    /'
file "$WORK${PREFIX}/bin/postgres" | grep -q "${ARCH_HINT}" \
    || { echo "!! postgres 不是 ${EXPECT_ARCH} ELF"; exit 1; }
echo "    psql / initdb / pg_dump 存在性:"
for b in psql initdb pg_dump pg_basebackup pg_ctl; do
    [ -f "$WORK${PREFIX}/bin/$b" ] || { echo "!! 缺少客户端/服务端二进制: $b"; exit 1; }
done
echo "        $(ls "$WORK${PREFIX}/bin" | wc -l) 个二进制在 ${PREFIX}/bin"

echo
echo "=================== 7. 版本自证 ======================="
if [ -x "$WORK${PREFIX}/bin/pg_config" ]; then
    echo "    pg_config --version: $(LD_LIBRARY_PATH="$WORK${PREFIX}/lib" "$WORK${PREFIX}/bin/pg_config" --version 2>/dev/null || echo '无法在本机执行')"
fi

echo
echo "=================== 8. 生成校验和与构建信息 ==========="
( cd "$TOP" && find RPMS SRPMS -name '*.rpm' | sort | xargs sha256sum > SHA256SUMS )
sed 's/^/    /' SHA256SUMS | sed -n '1,20p'

{
    echo "PostgreSQL ${PGVERSION} RPM build for ${TARGET_NAME}"
    echo "=============================================================="
    echo "build time   : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "source repo  : dreamalloc/postgres"
    echo "source ref   : official release tarball v${PGVERSION}"
    echo "source commit: $(cat /tmp/src_commit.txt 2>/dev/null || echo unknown)"
    echo "runner       : ${EXPECT_ARCH} / $(nproc) vCPU"
    echo "build rootfs : $(cat /etc/redhat-release 2>/dev/null || cat /etc/openEuler-release 2>/dev/null || echo unknown)"
    echo "gcc          : $(gcc --version | sed -n '1p')"
    echo "glibc        : $(ldd --version | sed -n '1p')"
    echo
    echo "Install on ${TARGET_NAME}"
    echo "----------------------------------"
    echo "  dnf install ./*.rpm              # 或 rpm -Uvh ./*.rpm"
    echo "  ${PREFIX}/bin/postgresql-${PGMAJOR}-setup initdb"
    echo "  systemctl enable --now postgresql-${PGMAJOR}"
    echo "  ${PREFIX}/bin/psql               # peer 认证，本地免密"
} > BUILD-INFO.txt
cat BUILD-INFO.txt | sed 's/^/    /'
