from cli.ceph.ceph import Ceph
from cli.exceptions import OperationFailedError
from utility.log import Log

log = Log(__name__)


def run(ceph_cluster, **kw):
    """Verify file lock operation
    Args:
        **kw: Key/value pairs of configuration information to be used in the test.
    """
    config = kw.get("config")
    nfs_nodes = ceph_cluster.get_nodes("nfs")
    clients = ceph_cluster.get_nodes("client")

    port = config.get("port", "2049")
    version = config.get("nfs_version", "4.0")

    nfs_node = nfs_nodes[0]

    fs_name = "cephfs"
    nfs_name = "cephfs-nfs"
    nfs_export = "/export"
    nfs_mount = "/mnt/nfs"
    fs = "cephfs"
    try:
        # Step 1: Enable nfs
        Ceph(clients[0]).mgr.module(action="enable", module="nfs", force=True)

        # Step 2: Create an NFS cluster
        nfs_server_name = nfs_node.hostname
        Ceph(clients[0]).nfs.cluster.create(name=nfs_name, nfs_server=nfs_server_name)

        # Step 3: Perform Export on clients
        for client in clients[:1]:
            Ceph(client).nfs.export.create(
                fs_name=fs_name, nfs_name=nfs_name, nfs_export=nfs_export, fs=fs
            )

        # Step 4: Perform nfs mount
        for client in clients:
            # Create mount dirs
            client.exec_command(cmd=f"mkdir -p {nfs_mount}", sudo=True)
            cmd = f"mount -t nfs -o vers={version},port={port} {nfs_server_name}:{nfs_export} {nfs_mount}"
            out, _ = client.exec_command(cmd=cmd, sudo=True)
            if out:
                raise OperationFailedError(f"Failed to mount nfs on {client.hostname}")

        # Step 5: Install bonnie++ on clients
        for client in clients:
            cmds = [
                "wget https://dl.fedoraproject.org/pub/epel/9/Everything/x86_64/Packages/b/bonnie++-2.00a-7.el9"
                ".x86_64.rpm",
                "yum install bonnie++-2.00a-7.el9.x86_64.rpm -y",
            ]
            for cmd in cmds:
                client.exec_command(cmd=cmd, sudo=True)

        # Step 6: Run Bonnie++ on all the clients
        ctr = 0
        for client in clients:
            folder_name = f"{nfs_mount}/test_folder_{str(ctr)}"
            cmds = [
                f"mkdir -p {folder_name}",
                f"chmod 777 {folder_name}",
                f"bonnie++ -d {folder_name} -u cephuser",
            ]
            ctr += 1
            for cmd in cmds:
                client.exec_command(cmd=cmd, sudo=True)
        log.info("Successfully completed pynfs tests on nfs cluster")
    except Exception as e:
        log.error(f"Error : {e}")
    finally:
        log.info("Cleaning up")
        for client in clients:
            client.exec_command(sudo=True, cmd=f"rm -rf {nfs_mount}/*")
            log.info("Unmounting nfs-ganesha mount on client:")
            client.exec_command(sudo=True, cmd=" umount %s -l" % (nfs_mount))
            log.info("Removing nfs-ganesha mount dir on client:")
            client.exec_command(sudo=True, cmd="rm -rf  %s" % (nfs_mount))
            client.exec_command(
                sudo=True,
                cmd=f"ceph nfs export delete {nfs_name} {nfs_export}",
                check_ec=False,
            )
            client.exec_command(
                sudo=True,
                cmd=f"ceph nfs cluster delete {nfs_name}",
                check_ec=False,
            )
            log.info("Cleaning up successfull")
    return 0
