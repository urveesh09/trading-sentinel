"""Process-scoped outbound-network guard for research entrypoints; no host setting changes."""
import sys
def deny_network(event,args):
    if event in ('socket.connect','socket.getaddrinfo','socket.bind'):
        raise PermissionError('round8 research is offline; network access forbidden')
sys.addaudithook(deny_network)
