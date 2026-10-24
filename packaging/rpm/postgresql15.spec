# ---------------------------------------------------------------------------
# PostgreSQL 15.17 RPM spec —— 与 MySQL 那套流水线同构，但 PG 用 autoconf
#
# 与发行版自带 postgresql 的差异：
#   - 前缀直接用 /usr（不是 PGDG 的 /usr/pgsql-13），与 MySQL 包风格一致
#   - 头文件收到 /usr/include/postgresql，避免污染 /usr/include/server
#   - 数据目录 /var/lib/pgsql/data，日志走 journald（不装 logging_collector）
#   - systemd 单元 Type=notify（PG 13 编译时 --with-systemd 会发 sd_notify）
# ---------------------------------------------------------------------------

%global pgmajor  15
%global srcname  postgresql-15.17

%global _binary_payload w2.xzdio

# openEuler 24.03（gcc 12）的告警抑制
%if 0%{?oe2403}
%global extra_warn -Wno-stringop-overflow -Wno-maybe-uninitialized -Wno-array-bounds
%else
%global extra_warn %{nil}
%endif

Name:           postgresql15
Version:        15.17
Release:        1%{?dist}
Summary:        PostgreSQL 15.17 relational database management system
License:        PostgreSQL
URL:            https://www.postgresql.org/
Source0:        %{srcname}.tar.gz

BuildRequires:  gcc make
BuildRequires:  readline-devel zlib-devel openssl-devel libxml2-devel libxslt-devel
BuildRequires:  gettext bison flex
BuildRequires:  perl perl-devel perl-ExtUtils-Embed python3-devel
BuildRequires:  systemd-devel
%if 0%{?oe2403}
BuildRequires:  rpm-build openEuler-rpm-config
%else
%if 0%{?kylin}
BuildRequires:  rpm-build kylin-rpm-config
%else
BuildRequires:  rpm-build redhat-rpm-config
%endif
%endif
BuildRequires:  findutils which tar gzip

%description
PostgreSQL 15.17，基于 postgres/postgres 的 REL_13_23 源码重新编译打包，
面向国产化 Linux（麒麟 V10 SP3 / openEuler 24.03）提供可离线安装的 RPM。

本包为 meta 包，实际内容见 postgresql15-server / -client / -libs / -contrib / -devel。

%package        libs
Summary:        PostgreSQL 15.17 客户端共享库
Obsoletes:      postgresql-libs < 13
Conflicts:      postgresql-libs

%description    libs
libpq / libecpg / libpgtypes 运行库。

%package        client
Summary:        PostgreSQL 15.17 客户端工具
Requires:       %{name}-libs%{?_isa} = %{version}-%{release}
Conflicts:      postgresql

%description    client
psql、pg_dump、pg_restore、pgbench 等命令行工具。

%package        server
Summary:        PostgreSQL 15.17 数据库服务端
Requires:       %{name}-client%{?_isa} = %{version}-%{release}
Requires:       %{name}-libs%{?_isa} = %{version}-%{release}
Requires:       shadow-utils coreutils
Requires(pre):  shadow-utils
Requires(post): systemd
Requires(preun): systemd
Requires(postun): systemd
Provides:       postgresql-server = %{version}-%{release}
Conflicts:      postgresql-server

%description    server
postgres 服务端进程、initdb、管理工具、systemd 单元与默认数据目录骨架。

首次启动时由 /usr/bin/postgresql-15-initdb 初始化数据目录（auth-local=peer，
auth-host=scram-sha-256），初始超级用户为 postgres。

%package        contrib
Summary:        PostgreSQL 15.17 附加扩展模块
Requires:       %{name}-server%{?_isa} = %{version}-%{release}

%description    contrib
hstore、pg_stat_statements、uuid-ossp 等官方扩展。

%package        devel
Summary:        PostgreSQL 15.17 开发头文件与库
Requires:       %{name}-libs%{?_isa} = %{version}-%{release}

%description    devel
libpq 头文件、pg_config、pgxs 构建框架与静态/动态链接库。

# ---------------------------------------------------------------------------
%prep
%setup -q -n %{srcname}

%build
%configure \
  --prefix=%{_prefix} \
  --libdir=%{_libdir} \
  --sysconfdir=%{_sysconfdir} \
  --datadir=%{_datadir}/postgresql/%{pgmajor} \
  --includedir=%{_includedir}/postgresql \
  --mandir=%{_mandir} \
  --with-openssl \
  --with-libxml \
  --with-zlib \
  --with-readline \
  --with-systemd \
  --with-system-tzdata=%{_datadir}/zoneinfo \
  --with-perl \
  --with-python \
  --enable-thread-safety \
  --with-pgport=5432 \
  CFLAGS="%{optflags} %{extra_warn}"

make %{?_smp_mflags}
make -C contrib %{?_smp_mflags}

%install
rm -rf %{buildroot}
make DESTDIR=%{buildroot} install
make -C contrib DESTDIR=%{buildroot} install

install -d -m 0700 %{buildroot}%{_localstatedir}/lib/pgsql/data
install -d -m 0755 %{buildroot}%{_localstatedir}/run/postgresql

# systemd 单元
install -d %{buildroot}%{_unitdir}
cat > %{buildroot}%{_unitdir}/postgresql-15.service <<'UNIT'
[Unit]
Description=PostgreSQL 15 database server
Documentation=https://www.postgresql.org/docs/13/
After=network.target
After=syslog.target

[Service]
Type=notify
User=postgres
Group=postgres
OOMScoreAdjust=-1000
Environment=PGDATA=/var/lib/pgsql/data
Environment=PG_OOM_ADJUST_FILE=/proc/self/oom_score_adj
Environment=PG_OOM_ADJUST_VALUE=0
ExecStartPre=/usr/bin/postgresql-15-initdb
ExecStart=/usr/bin/postgres -D ${PGDATA} -c config_file=${PGDATA}/postgresql.conf
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
KillSignal=SIGINT
TimeoutSec=300

[Install]
WantedBy=multi-user.target
UNIT

# 首次启动的初始化脚本
install -d %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/postgresql-15-initdb <<'INIT'
#!/bin/bash
# 首次启动自动 initdb；数据目录已有 PG_VERSION 则什么都不做
set -u
PGDATA="${PGDATA:-/var/lib/pgsql/data}"
PGCONF="${PGDATA}/postgresql.conf"

[ -f "${PGDATA}/PG_VERSION" ] && exit 0

# 目录必须存在且属 postgres
if [ ! -d "${PGDATA}" ] || [ ! -w "${PGDATA}" ]; then
    echo "postgresql-15-initdb: ${PGDATA} 不存在或不可写" >&2
    exit 1
fi

echo "postgresql-15-initdb: 初始化 ${PGDATA} ..."
/usr/bin/initdb -D "${PGDATA}" -U postgres \
    --auth-local=peer --auth-host=scram-sha-256 \
    --encoding=UTF8 --locale=C.UTF-8 >/dev/null || exit 1

# 只监听本地，避免装完就暴露
sed -i "s/^#listen_addresses.*/listen_addresses = 'localhost'/" "${PGCONF}" || :
sed -i "s/^#password_encryption.*/password_encryption = 'scram-sha-256'/" "${PGCONF}" || :
exit 0
INIT
chmod 0755 %{buildroot}%{_bindir}/postgresql-15-initdb

# 扩展的 DOCS 安装会留下空目录 /usr/share/doc/postgresql/extension，无人认领
rm -rf %{buildroot}%{_datadir}/doc/postgresql

find %{buildroot} -type f -o -type l | sed "s|%{buildroot}||" | sort > %{_builddir}/buildroot-files.txt

# ---------------------------------------------------------------------------
%pre server
getent group postgres >/dev/null 2>&1 || /usr/sbin/groupadd -r postgres >/dev/null 2>&1 || :
getent passwd postgres >/dev/null 2>&1 || \
    /usr/sbin/useradd -r -g postgres -d %{_localstatedir}/lib/pgsql -s /bin/bash \
        -c "PostgreSQL Server" postgres >/dev/null 2>&1 || :

%post server
%systemd_post postgresql-15.service
if [ $1 -eq 1 ]; then
    /usr/bin/systemctl enable postgresql-15.service >/dev/null 2>&1 || :
fi

%preun server
%systemd_preun postgresql-15.service

%postun server
%systemd_postun_with_restart postgresql-15.service

%post libs -p /sbin/ldconfig
%postun libs -p /sbin/ldconfig

# ---------------------------------------------------------------------------
%files
%doc COPYRIGHT README

%files libs
%{_libdir}/libpq.so.5*
%{_libdir}/libecpg.so.6*
%{_libdir}/libecpg_compat.so.3*
%{_libdir}/libpgtypes.so.3*

%files client
%{_bindir}/clusterdb
%{_bindir}/createdb
%{_bindir}/createuser
%{_bindir}/dropdb
%{_bindir}/dropuser
%{_bindir}/oid2name
%{_bindir}/pg_amcheck
%{_bindir}/pg_basebackup
%{_bindir}/pg_dump
%{_bindir}/pg_dumpall
%{_bindir}/pg_isready
%{_bindir}/pg_receivewal
%{_bindir}/pg_recvlogical
%{_bindir}/pg_restore
%{_bindir}/pgbench
%{_bindir}/psql
%{_bindir}/reindexdb
%{_bindir}/vacuumdb
%{_bindir}/vacuumlo

%files server
%{_bindir}/initdb
%{_bindir}/postgres
%{_bindir}/postmaster
%{_bindir}/pg_archivecleanup
%{_bindir}/pg_checksums
%{_bindir}/pg_controldata
%{_bindir}/pg_ctl
%{_bindir}/pg_resetwal
%{_bindir}/pg_rewind
%{_bindir}/pg_test_fsync
%{_bindir}/pg_test_timing
%{_bindir}/pg_upgrade
%{_bindir}/pg_verifybackup
%{_bindir}/pg_waldump
%{_bindir}/postgresql-15-initdb
%{_unitdir}/postgresql-15.service

# 全部共享模块（core + contrib 的 .so 同处 /usr/lib64/postgresql）
%dir %{_libdir}/postgresql
%{_libdir}/postgresql/*.so

%{_datadir}/postgresql/%{pgmajor}/*.bki
%{_datadir}/postgresql/%{pgmajor}/*.sample
%{_datadir}/postgresql/%{pgmajor}/*.sql
%{_datadir}/postgresql/%{pgmajor}/*.txt
# --with-system-tzdata 使用系统时区库，不安装 share/timezone
%{_datadir}/postgresql/%{pgmajor}/timezonesets/
%{_datadir}/postgresql/%{pgmajor}/tsearch_data/

%dir %attr(700, postgres, postgres) %{_localstatedir}/lib/pgsql/data
%dir %attr(755, postgres, postgres) %{_localstatedir}/run/postgresql

%files contrib
%{_datadir}/postgresql/%{pgmajor}/extension/

%files devel
%{_bindir}/pg_config
%{_bindir}/ecpg
%{_includedir}/postgresql/
%{_libdir}/libpq.so
%{_libdir}/libecpg.so
%{_libdir}/libecpg_compat.so
%{_libdir}/libpgtypes.so
%{_libdir}/libpq.a
%{_libdir}/libecpg.a
%{_libdir}/libecpg_compat.a
%{_libdir}/libpgtypes.a
%{_libdir}/libpgcommon.a
%{_libdir}/libpgcommon_shlib.a
%{_libdir}/libpgport.a
%{_libdir}/libpgport_shlib.a
%{_libdir}/libpgfeutils.a
%{_libdir}/pkgconfig/*.pc
%{_libdir}/postgresql/pgxs/

# ---------------------------------------------------------------------------
%changelog
* Sat Oct 24 2026 Build Team <ops@example.com> - 15.17-1
- 基于 postgres/postgres 标签 REL_15_17 构建
- 双平台：麒麟 V10 SP3 (aarch64) / openEuler 24.03 LTS (x86_64)
- systemd Type=notify（--with-systemd），首启自动 initdb
