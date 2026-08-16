import net from "net";

export function checkPort(port: number, host = "127.0.0.1"): Promise<boolean> {
  return new Promise((resolve) => {
    const server = net.createServer();

    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close();
      resolve(true);
    });

    server.listen(port, host);
  });
}

export async function findOpenPorts(
  ports: number[] = [
    80, 443, 3000, 3001, 4000, 4200, 5000, 5173, 5500, 6000,
    6379, 7262, 8000, 8080, 8443, 8888, 9000, 9090,
  ]
): Promise<number[]> {
  const openPorts: number[] = [];
  await Promise.all(
    ports.map(async (port) => {
      if (await checkPort(port)) openPorts.push(port);
    })
  );
  return openPorts.sort((a, b) => a - b);
}
