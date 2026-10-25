#!/usr/bin/env bash
# openEuler / EL8 通用：PostgreSQL 13.23 构建依赖
# BOOST 之类的第三方源码 PG 不需要，依赖比 MySQL 少很多
set -eu
if [ -n "${BASH_VERSION:-}" ]; then set +o pipefail; fi

echo "==> 系统信息"
cat /etc/rocky-release 2>/dev/null || cat /etc/openEuler-release 2>/dev/null || cat /etc/os-release | sed -n '1,3p'

echo "==> 安装构建依赖"
dnf -y makecache >/dev/null 2>&1 || :
dnf -y --setopt=install_weak_deps=False --setopt=keepcache=1 install \
    gcc gcc-c++ make \
    readline-devel zlib-devel openssl-devel libxml2-devel libxslt-devel \
    lz4-devel zstd-devel tcl-devel libuuid-devel \
    gettext bison flex \
    perl perl-devel perl-ExtUtils-Embed python3-devel \
    systemd-devel \
    rpm-build \
    tar gzip which findutils diffutils file cpio procps-ng shadow-utils

# rpm 宏包：EL8 叫 redhat-rpm-config，openEuler 叫 openEuler-rpm-config
if dnf -y install redhat-rpm-config >/dev/null 2>&1; then
    echo "    rpm-config: redhat-rpm-config"
elif dnf -y install openEuler-rpm-config >/dev/null 2>&1; then
    echo "    rpm-config: openEuler-rpm-config"
else
    echo "    !! 未找到 rpm 宏包，%systemd_post 可能不可用"
fi
dnf -y install systemd-rpm-macros >/dev/null 2>&1 || :

dnf clean all >/dev/null 2>&1 || :
rm -rf /var/cache/dnf

echo "==> 组件版本"
gcc --version | sed -n '1p'
make --version | sed -n '1p'
ldd --version | sed -n '1p'
rpm --version

# --- 官方源码包（PGDG 布局需要 tarball 内的预生成 man 页）---
PGVERSION="${PGVERSION:?需要 PGVERSION，如 15.17}"
SRC_TARBALL_NAME="${SRC_TARBALL_NAME:-postgresql-${PGVERSION}.tar.bz2}"
SRC_CACHE="${SRC_CACHE:-/var/cache/pgsrc}"
SRC_TARBALL="${SRC_CACHE}/${SRC_TARBALL_NAME}"
mkdir -p "${SRC_CACHE}"
if [ ! -s "${SRC_TARBALL}" ]; then
    echo "==> 下载源码包 ${SRC_TARBALL_NAME}"
    curl -fL --retry 3 --connect-timeout 20 \
        -o "${SRC_TARBALL}.part" \
        "https://download.postgresql.org/pub/source/v${PGVERSION}/${SRC_TARBALL_NAME}"
    mv -f "${SRC_TARBALL}.part" "${SRC_TARBALL}"
fi
tar -tf "${SRC_TARBALL}" >/dev/null
echo "    OK: $(du -h "${SRC_TARBALL}" | cut -f1)  ${SRC_TARBALL}"
