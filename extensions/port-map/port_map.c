/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Explicit port publication for native ARM64 guests. No network namespace is created. */
#include <arpa/inet.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <talloc.h>

#include "extension/extension.h"
#include "tracee/abi.h"
#include "tracee/mem.h"

#define MAX_MAPS 64
typedef struct {
        uint16_t guest[MAX_MAPS], host[MAX_MAPS];
        size_t count;
        socklen_t capacity;
        socklen_t message_capacity[1024];
        size_t message_count;
} PortMap;

static const FilteredSysnum port_sysnums[] = {
        { PR_bind, FILTER_SYSEXIT }, { PR_connect, FILTER_SYSEXIT },
        { PR_sendto, FILTER_SYSEXIT }, { PR_getsockname, FILTER_SYSEXIT },
        { PR_getpeername, FILTER_SYSEXIT }, { PR_recvfrom, FILTER_SYSEXIT },
        { PR_sendmsg, FILTER_SYSEXIT }, { PR_sendmmsg, FILTER_SYSEXIT },
        { PR_recvmsg, FILTER_SYSEXIT }, { PR_recvmmsg, FILTER_SYSEXIT },
        FILTERED_SYSNUM_END
};

/* Parsing deliberately accepts decimal digits only, with no signs or whitespace. */
static int port_number(const char **cursor, uint16_t *port)
{
        unsigned value = 0;
        const char *p = *cursor;
        if (*p < '0' || *p > '9') return -EINVAL;
        do {
                value = value * 10 + (*p++ - '0');
                if (value > 65535) return -EINVAL;
        } while (*p >= '0' && *p <= '9');
        if (!value) return -EINVAL;
        *port = value;
        *cursor = p;
        return 0;
}

static int parse_map(PortMap *map, const char *value)
{
        if (!value || !*value) return -EINVAL;
        while (*value) {
                uint16_t guest, host;
                if (map->count == MAX_MAPS || port_number(&value, &guest) < 0 || *value++ != ':' ||
                    port_number(&value, &host) < 0 || host < 1024) return -EINVAL;
                for (size_t n = 0; n < map->count; n++)
                        if (map->guest[n] == guest || map->host[n] == host) return -EINVAL;
                map->guest[map->count] = guest;
                map->host[map->count++] = host;
                if (!*value) break;
                if (*value++ != ',' || !*value) return -EINVAL;
        }
        return 0;
}

/* Read only the supplied length; never mutate a caller's input sockaddr. */
static int translate(Tracee *tracee, PortMap *map, word_t *address, word_t length,
                     bool reverse, bool local_only)
{
        struct sockaddr_storage storage = {0};
        uint16_t *port;
        bool local;
        int status;
        if (!*address || length < sizeof(sa_family_t) || length > sizeof(storage)) return 0;
        status = read_data(tracee, &storage, *address, length);
        if (status < 0) return status;
        if (storage.ss_family == AF_INET && length >= sizeof(struct sockaddr_in)) {
                struct sockaddr_in *ip = (void *)&storage;
                port = &ip->sin_port;
                local = (ntohl(ip->sin_addr.s_addr) >> 24) == 127;
        } else if (storage.ss_family == AF_INET6 && length >= sizeof(struct sockaddr_in6)) {
                struct sockaddr_in6 *ip = (void *)&storage;
                port = &ip->sin6_port;
                local = IN6_IS_ADDR_LOOPBACK(&ip->sin6_addr) ||
                        (IN6_IS_ADDR_V4MAPPED(&ip->sin6_addr) && ip->sin6_addr.s6_addr[12] == 127);
        } else return 0;
        if (local_only && !local) return 0;
        for (size_t n = 0; n < map->count; n++) {
                if (ntohs(*port) != (reverse ? map->host[n] : map->guest[n])) continue;
                *port = htons(reverse ? map->guest[n] : map->host[n]);
                if (!reverse) {
                        *address = alloc_mem(tracee, length);
                        if (!*address) return -EFAULT;
                }
                status = write_data(tracee, *address, &storage, length);
                return status < 0 ? status : 1;
        }
        return 0;
}

static int input_address(Tracee *tracee, PortMap *map, Reg reg, Reg len, bool local_only)
{
        word_t address = peek_reg(tracee, CURRENT, reg);
        int status = translate(tracee, map, &address, peek_reg(tracee, CURRENT, len), false, local_only);
        if (status > 0) poke_reg(tracee, reg, address);
        return status < 0 ? status : 0;
}

/* The msghdr ABI is native here; the Android app runs ARM64 images only. */
static int message_address(Tracee *tracee, PortMap *map, bool batch)
{
        word_t original = peek_reg(tracee, CURRENT, SYSARG_2);
        word_t count = batch ? peek_reg(tracee, CURRENT, SYSARG_3) : 1;
        size_t stride = batch ? sizeof(struct mmsghdr) : sizeof(struct msghdr);
        if (!original || !count || count > 1024) return 0;
        void *headers = talloc_size(tracee->ctx, count * stride);
        if (!headers) return -ENOMEM;
        int status = read_data(tracee, headers, original, count * stride);
        if (status < 0) return status;
        bool changed = false;
        for (word_t n = 0; n < count; n++) {
                struct msghdr *msg = (void *)((char *)headers + n * stride);
                word_t address = (word_t)msg->msg_name;
                status = translate(tracee, map, &address, msg->msg_namelen, false, true);
                if (status < 0) return status;
                if (status > 0) { msg->msg_name = (void *)address; changed = true; }
        }
        if (!changed) return 0;
        word_t copy = alloc_mem(tracee, count * stride);
        if (!copy) return -EFAULT;
        status = write_data(tracee, copy, headers, count * stride);
        if (status < 0) return status;
        poke_reg(tracee, SYSARG_2, copy);
        return 0;
}

static int received_message(Tracee *tracee, PortMap *map, bool entering, bool batch)
{
        size_t stride = batch ? sizeof(struct mmsghdr) : sizeof(struct msghdr);
        word_t original = peek_reg(tracee, ORIGINAL, SYSARG_2);
        word_t count = entering ? (batch ? peek_reg(tracee, ORIGINAL, SYSARG_3) : 1) :
                                 (batch ? peek_reg(tracee, CURRENT, SYSARG_RESULT) : 1);
        if (entering) map->message_count = 0;
        if (!original || count > 1024 || (!entering && count > map->message_count)) return 0;
        for (word_t n = 0; n < count; n++) {
                struct msghdr header;
                int status = read_data(tracee, &header, original + n * stride, sizeof(header));
                if (status < 0) return entering ? 0 : status;
                if (entering) {
                        map->message_capacity[n] = header.msg_namelen;
                        map->message_count++;
                } else {
                        word_t address = (word_t)header.msg_name;
                        socklen_t size = header.msg_namelen;
                        if (size > map->message_capacity[n]) size = map->message_capacity[n];
                        status = translate(tracee, map, &address, size, true, true);
                        if (status < 0) return status;
                }
        }
        return 0;
}

int port_map_callback(Extension *extension, ExtensionEvent event, intptr_t data1, intptr_t data2 UNUSED)
{
        Tracee *tracee = TRACEE(extension);
        PortMap *map = extension->config;
        if (event == INITIALIZATION) {
                /* Multiple independent mapping extensions could translate a port twice. */
                Extension *other;
                LIST_FOREACH(other, tracee->extensions, link)
                        if (other != extension && other->callback == port_map_callback) return -EINVAL;
                map = talloc_zero(extension, PortMap);
                if (!map) return -ENOMEM;
                extension->config = map;
                extension->filtered_sysnums = port_sysnums;
                return parse_map(map, (const char *)data1);
        }
        if (event == INHERIT_PARENT) return 1;
        if (event == INHERIT_CHILD) {
                Extension *parent = (void *)data1;
                extension->config = talloc_memdup(extension, parent->config, sizeof(PortMap));
                extension->filtered_sysnums = port_sysnums;
                return extension->config ? 0 : -ENOMEM;
        }
        if ((event != SYSCALL_ENTER_END && event != SYSCALL_EXIT_END) ||
            !map || get_abi(tracee) != ABI_DEFAULT) return 0;
        Sysnum sysnum = get_sysnum(tracee, ORIGINAL);
        if (event == SYSCALL_ENTER_END) {
                switch (sysnum) {
                case PR_bind: return input_address(tracee, map, SYSARG_2, SYSARG_3, false);
                case PR_connect: return input_address(tracee, map, SYSARG_2, SYSARG_3, true);
                case PR_sendto: return input_address(tracee, map, SYSARG_5, SYSARG_6, true);
                case PR_sendmsg: return message_address(tracee, map, false);
                case PR_sendmmsg: return message_address(tracee, map, true);
                case PR_recvmsg: return received_message(tracee, map, true, false);
                case PR_recvmmsg: return received_message(tracee, map, true, true);
                case PR_getsockname: case PR_getpeername: case PR_recvfrom: {
                        word_t length = peek_reg(tracee, ORIGINAL, sysnum == PR_recvfrom ? SYSARG_6 : SYSARG_3);
                        map->capacity = 0;
                        if (length) read_data(tracee, &map->capacity, length, sizeof(map->capacity));
                        return 0;
                }
                default: return 0;
                }
        }
        if (event == SYSCALL_EXIT_END && (int)peek_reg(tracee, CURRENT, SYSARG_RESULT) >= 0) {
                if (sysnum == PR_recvmsg || sysnum == PR_recvmmsg)
                        return received_message(tracee, map, false, sysnum == PR_recvmmsg);
                if (sysnum == PR_getsockname || sysnum == PR_getpeername || sysnum == PR_recvfrom) {
                        word_t address = peek_reg(tracee, ORIGINAL, sysnum == PR_recvfrom ? SYSARG_5 : SYSARG_2);
                        word_t length = peek_reg(tracee, ORIGINAL, sysnum == PR_recvfrom ? SYSARG_6 : SYSARG_3);
                        socklen_t size;
                        if (!length || !map->capacity) return 0;
                        int status = read_data(tracee, &size, length, sizeof(size));
                        if (status < 0) return status;
                        if (size > map->capacity) size = map->capacity;
                        status = translate(tracee, map, &address, size, true, sysnum != PR_getsockname);
                        return status < 0 ? status : 0;
                }
                /* sendmmsg writes msg_len back into the copied array. */
                if (sysnum == PR_sendmmsg && peek_reg(tracee, ORIGINAL, SYSARG_2) != peek_reg(tracee, MODIFIED, SYSARG_2)) {
                        word_t count = peek_reg(tracee, CURRENT, SYSARG_RESULT);
                        for (word_t n = 0; n < count; n++) {
                                unsigned length;
                                size_t offset = n * sizeof(struct mmsghdr) + offsetof(struct mmsghdr, msg_len);
                                int status = read_data(tracee, &length, peek_reg(tracee, MODIFIED, SYSARG_2) + offset, sizeof(length));
                                if (status < 0) return status;
                                status = write_data(tracee, peek_reg(tracee, ORIGINAL, SYSARG_2) + offset, &length, sizeof(length));
                                if (status < 0) return status;
                        }
                }
        }
        return 0;
}
