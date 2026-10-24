#!/usr/bin/env bash
# openEuler 24.03 LTS 专用：PostgreSQL 13.23 构建依赖
# BOOST 之类的第三方源码 PG 不需要，依赖比 MySQL 少很多
set -eu
if [ -n "${BASH_VERSION:-}" ]; then set +o pipefail; fi

echo "==> 系统信息"
cat /etc/openEuler-release 2>/dev/null || cat /etc/os-release | sed -n '1,3p'

echo "==> 安装构建依赖"
dnf -y makecache >/dev/null 2>&1 || :
dnf -y --setopt=install_weak_deps=False --setopt=keepcache=1 install \
    gcc gcc-c++ make \
    readline-devel zlib-devel openssl-devel libxml2-devel libxslt-devel \
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

# 保留 /var/cache/dnf 供 actions/cache 复用
dnf clean metadata >/dev/null 2>&1 || :

echo "==> 组件版本"
gcc --version | sed -n '1p'
make --version | sed -n '1p'
ldd --version | sed -n '1p'
rpm --version
