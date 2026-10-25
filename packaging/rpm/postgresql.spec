# ---------------------------------------------------------------------------
# PostgreSQL RPM spec —— 按 PGDG 官方布局实现
#
# 与官方 srpm（postgresql13-13.23 / postgresql15-15.17 PGDG）一致的要点：
#   - 隔离前缀 /usr/pgsql-XX（不污染 /usr/bin、/usr/lib64）
#   - 数据目录 /var/lib/pgsql/XX/{data,backups}（带大版本号，可多版本共存）
#   - postgresql-XX-setup initdb 显式初始化，首启由 check-db-dir 校验
#   - 子包拆分：main / libs / server / docs / contrib / devel / plperl /
#     plpython3 / pltcl（llvmjit、test 默认关闭，可用 --define 打开）
#   - Source0 用官方 release tarball（含预生成 man 页）
#
# 构建时传入：--define "pgmajor 15" --define "pgversion 15.17"
# ---------------------------------------------------------------------------

%global pgmajor    %{?pgmajor}%{!?pgmajor:15}
%global pgversion  %{?pgversion}%{!?pgversion:15.17}
%global sname      postgresql
%global baseinstdir /usr/pgsql-%{pgmajor}
%global pgdatadir  /var/lib/pgsql/%{pgmajor}

%if "%{pgmajor}" == "15"
%global prevmajor 14
%else
%global prevmajor 12
%endif

# 可选组件（默认关掉，避免引入 llvm/tcl 的版本风险）
%global with_llvm   %{?with_llvm}%{!?with_llvm:0}
%global with_plperl %{?with_plperl}%{!?with_plperl:1}
%global with_pltcl  %{?with_pltcl}%{!?with_pltcl:1}
%global with_test   %{?with_test}%{!?with_test:0}
# 调试包：默认生成 debuginfo 与 debugsource；瘦身构建可 --define "with_debug 0"
%global with_debug   %{?with_debug}%{!?with_debug:1}

%global _binary_payload w2.xzdio
%if "%{with_debug}" == "0"
%global debug_package %{nil}
%endif

%if 0%{?oe2403}
%global extra_warn -Wno-stringop-overflow -Wno-maybe-uninitialized -Wno-array-bounds
%else
%global extra_warn %{nil}
%endif

Name:           postgresql%{pgmajor}
Version:        %{pgversion}
Release:        1%{?dist}
Summary:        PostgreSQL %{pgversion} relational database management system
License:        PostgreSQL
URL:            https://www.postgresql.org/
Source0:        https://download.postgresql.org/pub/source/v%{pgversion}/%{sname}-%{pgversion}.tar.bz2
Source1:        postgresql.service.in
# Source1 取自 PGDG 官方 SRPM 的 postgresql-XX.service，13/15 共用一个模板，
# 构建时把 @PGMAJOR@ 替换成大版本号（官方 13 版单元没有 Restart=on-failure，此处统一保留）

BuildRequires:  gcc make
BuildRequires:  readline-devel zlib-devel openssl-devel libxml2-devel libxslt-devel
BuildRequires:  lz4-devel zstd-devel libuuid-devel
BuildRequires:  gettext bison flex
BuildRequires:  perl perl-devel perl-ExtUtils-Embed python3-devel
%if %{with_pltcl}
BuildRequires:  tcl-devel
%endif
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
BuildRequires:  findutils which tar gzip bzip2

%description
PostgreSQL %{pgversion}，按 PGDG 官方布局打包（前缀 /usr/pgsql-%{pgmajor}），
面向国产化 Linux（麒麟 V10 SP3 / openEuler 24.03）。

本包为 meta 包，实际内容见 postgresql%{pgmajor}-server / -client(main) / -libs 等。

%package        libs
Summary:        The shared libraries required for any PostgreSQL client
Obsoletes:      postgresql-libs < %{pgmajor}
Conflicts:      postgresql-libs

%description    libs
libpq / libecpg / libpgtypes 运行库与 libpqwalreceiver 模块。

%package        server
Summary:        The programs needed to create and run a PostgreSQL server
Requires:       postgresql%{pgmajor}-libs%{?_isa} = %{version}-%{release}
Requires:       shadow-utils coreutils
Requires(pre):  shadow-utils
Requires(post): systemd
Requires(preun): systemd
Requires(postun): systemd
Provides:       %{sname}-server = %{version}-%{release}

%description    server
postgres 服务端、initdb、管理工具、systemd 单元与数据目录骨架。

安装后执行 `postgresql-%{pgmajor}-setup initdb` 初始化数据目录，
再 `systemctl enable --now postgresql-%{pgmajor}`。

%package        docs
Summary:        Extra documentation for PostgreSQL
BuildArch:      noarch

%description    docs
PG 文档源码与教程。

%package        contrib
Summary:        Contributed source and binaries distributed with PostgreSQL
Requires:       postgresql%{pgmajor}-server%{?_isa} = %{version}-%{release}

%description    contrib
hstore、pg_stat_statements、uuid-ossp、amcheck 等官方扩展。

%package        devel
Summary:        PostgreSQL development header files and libraries
Requires:       postgresql%{pgmajor}-libs%{?_isa} = %{version}-%{release}

%description    devel
libpq 头文件、pg_config、pgxs、静态库与 pkgconfig。

%if %{with_plperl}
%package        plperl
Summary:        The Perl procedural language for PostgreSQL
Requires:       postgresql%{pgmajor}-server%{?_isa} = %{version}-%{release}
%description    plperl
PL/Perl 过程语言。
%endif

%package        plpython3
Summary:        The Python3 procedural language for PostgreSQL
Requires:       postgresql%{pgmajor}-server%{?_isa} = %{version}-%{release}
%description    plpython3
PL/Python3 过程语言。

%if %{with_pltcl}
%package        pltcl
Summary:        The Tcl procedural language for PostgreSQL
Requires:       postgresql%{pgmajor}-server%{?_isa} = %{version}-%{release}
%description    pltcl
PL/Tcl 过程语言。
%endif

# ---------------------------------------------------------------------------
%prep
%setup -q -n %{sname}-%{pgversion}

%build
%if 0%{?kylin}
CFLAGS="%{optflags} %{extra_warn}"
%else
CFLAGS="%{optflags} %{extra_warn}"
%endif

./configure --enable-rpath \
    --prefix=%{baseinstdir} \
    --includedir=%{baseinstdir}/include \
    --mandir=%{baseinstdir}/share/man \
    --datadir=%{baseinstdir}/share \
    --libdir=%{baseinstdir}/lib \
    --with-openssl \
    --with-libxml --with-libxslt \
    --with-zlib --with-lz4 --with-zstd \
    --with-readline \
    --with-systemd \
    --with-system-tzdata=%{_datadir}/zoneinfo \
    --with-perl --with-python \
%if %{with_pltcl}
    --with-tcl --with-tclconfig=%{_libdir} \
%endif
    --with-uuid=e2fs \
    --enable-thread-safety \
    --with-pgport=5432 \
    CFLAGS="$CFLAGS"

make %{?_smp_mflags}
make -C contrib %{?_smp_mflags}

%install
rm -rf %{buildroot}
make DESTDIR=%{buildroot} install
make -C contrib DESTDIR=%{buildroot} install

# --- 数据目录骨架 ---
install -d -m 700 %{buildroot}/var/lib/pgsql
install -d -m 700 %{buildroot}%{pgdatadir}
install -d -m 700 %{buildroot}%{pgdatadir}/data
install -d -m 700 %{buildroot}%{pgdatadir}/backups
install -d -m 755 %{buildroot}%{_rundir}/%{sname}
install -d -m 755 %{buildroot}/etc/sysconfig/pgsql

# --- setup 脚本（官方同名同语义，简化实现）---
cat > %{buildroot}%{baseinstdir}/bin/%{sname}-%{pgmajor}-setup <<'SETUP'
#!/bin/bash
# postgresql-XX-setup <initdb|...>
set -u
PGMAJOR="__PGMAJOR__"
PGDATA="/var/lib/pgsql/${PGMAJOR}/data"
BIN="/usr/pgsql-${PGMAJOR}/bin"

case "${1:-}" in
  initdb)
    [ -f "${PGDATA}/PG_VERSION" ] && { echo "数据目录已初始化: ${PGDATA}"; exit 0; }
    "${BIN}/initdb" -D "${PGDATA}" -U postgres \
        --auth-local=peer --auth-host=scram-sha-256 \
        --encoding=UTF8 --locale=C.UTF-8 || exit 1
    sed -i "s/^#listen_addresses.*/listen_addresses = 'localhost'/" "${PGDATA}/postgresql.conf" || :
    sed -i "s/^#password_encryption.*/password_encryption = 'scram-sha-256'/" "${PGDATA}/postgresql.conf" || :
    echo "初始化完成: ${PGDATA}"
    ;;
  *)
    echo "用法: $0 initdb" >&2
    exit 2
    ;;
esac
SETUP
sed -i "s/__PGMAJOR__/%{pgmajor}/" %{buildroot}%{baseinstdir}/bin/%{sname}-%{pgmajor}-setup
chmod 0755 %{buildroot}%{baseinstdir}/bin/%{sname}-%{pgmajor}-setup

# /usr/bin 下放软链，便于直接调用
mkdir -p %{buildroot}%{_bindir}
ln -sf %{baseinstdir}/bin/%{sname}-%{pgmajor}-setup %{buildroot}%{_bindir}/%{sname}-%{pgmajor}-setup

# --- check-db-dir ---
cat > %{buildroot}%{baseinstdir}/bin/%{sname}-%{pgmajor}-check-db-dir <<'CHK'
#!/bin/bash
set -u
PGDATA="${1:-/var/lib/pgsql/__PGMAJOR__/data}"
if [ ! -f "${PGDATA}/PG_VERSION" ]; then
    echo "没有找到已初始化的数据目录: ${PGDATA}" >&2
    echo "请先执行: postgresql-__PGMAJOR__-setup initdb" >&2
    exit 1
fi
exit 0
CHK
sed -i "s/__PGMAJOR__/%{pgmajor}/g" %{buildroot}%{baseinstdir}/bin/%{sname}-%{pgmajor}-check-db-dir
chmod 0755 %{buildroot}%{baseinstdir}/bin/%{sname}-%{pgmajor}-check-db-dir

# --- systemd unit（官方 PGDG 单元模板，路径全部由 pgmajor 推导）---
install -d %{buildroot}%{_unitdir}
sed -e 's/@PGMAJOR@/%{pgmajor}/g' %{SOURCE1} > %{buildroot}%{_unitdir}/%{sname}-%{pgmajor}.service
chmod 0644 %{buildroot}%{_unitdir}/%{sname}-%{pgmajor}.service

# --- tmpfiles ---
install -d %{buildroot}%{_prefix}/lib/tmpfiles.d
cat > %{buildroot}%{_prefix}/lib/tmpfiles.d/%{sname}-%{pgmajor}.conf <<'TMPF'
d /run/postgresql 0755 postgres postgres -
TMPF

find %{buildroot} -type f -o -type l | sed "s|%{buildroot}||" | sort > %{_builddir}/buildroot-files.txt

# --- 生成各子包文件清单 -----------------------------------------------------
# 与 PGDG 官方 spec 同思路：不在 files 段里硬编码文件路径，而是在 install
# 阶段遍历 buildroot，把每个条目按规则归入唯一子包，写出 *.lst 交给
# 阶段生成清单交给 -f 使用。13/15 两个大版本、麒麟/openEuler 两个平台共用
# spec，不会因为某版本多/少一个模块（pg_walinspect、pg_surgery、pg_standby…）
# 就报 File not found 或 Installed (but unpackaged)。
LSTDIR=%{_builddir}/lst
rm -rf "$LSTDIR"
mkdir -p "$LSTDIR"
for p in main libs server contrib devel plperl plpython3 pltcl; do
    : > "$LSTDIR/$p.lst"
done
: > "$LSTDIR/_fallback.txt"

BASE=%{baseinstdir}
BR=%{buildroot}

find "$BR" -mindepth 1 \( -type f -o -type l -o -type d \) | LC_ALL=C sort > "$LSTDIR/.entries"

while IFS= read -r p; do
    rel="${p#$BR}"
    if [ -d "$p" ]; then
        case "$rel" in
            /var/lib/pgsql|%{pgdatadir}|%{pgdatadir}/data|%{pgdatadir}/backups)
                echo "%attr(700,postgres,postgres) %dir $rel" >> "$LSTDIR/server.lst" ;;
            /etc/sysconfig/pgsql)
                echo "%attr(755,root,root) %dir $rel" >> "$LSTDIR/server.lst" ;;
            %{_rundir}/%{sname})
                echo "%attr(755,postgres,postgres) %dir $rel" >> "$LSTDIR/server.lst" ;;
            *)
                if [ -z "$(ls -A "$p" 2>/dev/null)" ]; then
                    echo "$rel" >> "$LSTDIR/_fallback.txt"
                    echo "%dir $rel" >> "$LSTDIR/server.lst"
                fi ;;
        esac
        continue
    fi
    case "$rel" in
        %{_unitdir}/*|%{_prefix}/lib/tmpfiles.d/*)
            echo "$rel" >> "$LSTDIR/server.lst" ;;
        %{_bindir}/%{sname}-%{pgmajor}-setup)
            echo "$rel" >> "$LSTDIR/server.lst" ;;
        "$BASE"/share/man/*)
            echo "$rel" >> "$LSTDIR/main.lst" ;;
        "$BASE"/share/extension/plpgsql*)
            echo "$rel" >> "$LSTDIR/server.lst" ;;
        "$BASE"/share/extension/*plperl*)
            echo "$rel" >> "$LSTDIR/plperl.lst" ;;
        "$BASE"/share/extension/*plpython*)
            echo "$rel" >> "$LSTDIR/plpython3.lst" ;;
        "$BASE"/share/extension/*pltcl*)
            echo "$rel" >> "$LSTDIR/pltcl.lst" ;;
        "$BASE"/share/extension/*)
            echo "$rel" >> "$LSTDIR/contrib.lst" ;;
        "$BASE"/lib/*plperl*.so*)
            echo "$rel" >> "$LSTDIR/plperl.lst" ;;
        "$BASE"/lib/*plpython3*.so*)
            echo "$rel" >> "$LSTDIR/plpython3.lst" ;;
        "$BASE"/lib/*pltcl*.so*)
            echo "$rel" >> "$LSTDIR/pltcl.lst" ;;
        "$BASE"/lib/libpq.so.*|"$BASE"/lib/libecpg.so.*|"$BASE"/lib/libecpg_compat.so.*|"$BASE"/lib/libpgtypes.so.*|"$BASE"/lib/libpqwalreceiver.so)
            echo "$rel" >> "$LSTDIR/libs.lst" ;;
        "$BASE"/lib/*.so.*)
            echo "$rel" >> "$LSTDIR/libs.lst" ;;
        "$BASE"/include/*)
            echo "$rel" >> "$LSTDIR/devel.lst" ;;
        "$BASE"/bin/ecpg)
            echo "$rel" >> "$LSTDIR/devel.lst" ;;
        "$BASE"/lib/pgxs*|"$BASE"/lib/pkgconfig*|"$BASE"/lib/*.a)
            echo "$rel" >> "$LSTDIR/devel.lst" ;;
        "$BASE"/lib/libpq.so|"$BASE"/lib/libecpg.so|"$BASE"/lib/libecpg_compat.so|"$BASE"/lib/libpgtypes.so)
            echo "$rel" >> "$LSTDIR/devel.lst" ;;
        "$BASE"/lib/plpgsql.so|"$BASE"/lib/dict_*.so|"$BASE"/lib/pgoutput.so|"$BASE"/lib/euc*.so)
            echo "$rel" >> "$LSTDIR/server.lst" ;;
        "$BASE"/lib/*.so)
            echo "$rel" >> "$LSTDIR/contrib.lst" ;;
        "$BASE"/bin/postgres|"$BASE"/bin/postmaster|"$BASE"/bin/initdb|"$BASE"/bin/pg_ctl|"$BASE"/bin/pg_archivecleanup|"$BASE"/bin/pg_checksums|"$BASE"/bin/pg_controldata|"$BASE"/bin/pg_resetwal|"$BASE"/bin/pg_rewind|"$BASE"/bin/pg_test_fsync|"$BASE"/bin/pg_test_timing|"$BASE"/bin/pg_upgrade|"$BASE"/bin/pg_verifybackup|"$BASE"/bin/pg_amcheck|"$BASE"/bin/postgresql-*-setup|"$BASE"/bin/postgresql-*-check-db-dir)
            echo "$rel" >> "$LSTDIR/server.lst" ;;
        "$BASE"/bin/*)
            echo "$rel" >> "$LSTDIR/main.lst" ;;
        "$BASE"/share/postgres.bki|"$BASE"/share/*.sql|"$BASE"/share/*.txt|"$BASE"/share/*.sample|"$BASE"/share/timezonesets/*|"$BASE"/share/tsearch_data/*)
            echo "$rel" >> "$LSTDIR/server.lst" ;;
        "$BASE"/share/*)
            echo "$rel" >> "$LSTDIR/main.lst" ;;
        *)
            echo "$rel" >> "$LSTDIR/main.lst"
            echo "$rel" >> "$LSTDIR/_fallback.txt" ;;
    esac
done < "$LSTDIR/.entries"

echo "==> 子包文件清单："
for p in main libs server contrib devel plperl plpython3 pltcl; do
    printf '    %-10s %4s\n' "$p" "$(wc -l < "$LSTDIR/$p.lst")"
done
if [ -s "$LSTDIR/_fallback.txt" ]; then
    echo "==> 未明确归类、已并入 main/server 的条目："
    sed 's/^/      /' "$LSTDIR/_fallback.txt"
fi

# ---------------------------------------------------------------------------
%pre server
getent group postgres >/dev/null 2>&1 || /usr/sbin/groupadd -r postgres >/dev/null 2>&1 || :
getent passwd postgres >/dev/null 2>&1 || \
    /usr/sbin/useradd -r -g postgres -d /var/lib/pgsql -s /bin/bash \
        -c "PostgreSQL Server" postgres >/dev/null 2>&1 || :

%post server
%systemd_post %{sname}-%{pgmajor}.service

%preun server
%systemd_preun %{sname}-%{pgmajor}.service

%postun server
%systemd_postun_with_restart %{sname}-%{pgmajor}.service

%post libs -p /sbin/ldconfig
%postun libs -p /sbin/ldconfig

# ---------------------------------------------------------------------------
%files -f %{_builddir}/lst/main.lst

%files libs -f %{_builddir}/lst/libs.lst

%files server -f %{_builddir}/lst/server.lst

%files docs
%doc README
%doc COPYRIGHT
%doc doc/src

%files contrib -f %{_builddir}/lst/contrib.lst

%files devel -f %{_builddir}/lst/devel.lst

%files plperl -f %{_builddir}/lst/plperl.lst

%files plpython3 -f %{_builddir}/lst/plpython3.lst

%if %{with_pltcl}
%files pltcl -f %{_builddir}/lst/pltcl.lst
%endif

%changelog
* Sun Oct 25 2026 Build Team <ops@example.com> - %{pgversion}-1
- 改为 PGDG 官方布局：/usr/pgsql-%{pgmajor} 前缀、/var/lib/pgsql/%{pgmajor}/data、
  postgresql-%{pgmajor}-setup initdb、10 子包结构、Source0 用官方 release tarball
