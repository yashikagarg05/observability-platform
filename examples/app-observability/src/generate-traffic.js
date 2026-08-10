const baseUrl = process.env.ORDERS_API_URL || "http://localhost:18080";

const paths = ["/", "/health", "/api/orders", "/api/orders", "/api/error"];

async function main() {
  for (const path of paths) {
    const url = `${baseUrl}${path}`;
    try {
      const response = await fetch(url);
      const body = await response.text();
      console.log(`${response.status} ${path} ${body.slice(0, 120)}`);
    } catch (error) {
      console.error(`request failed ${path}: ${error.message}`);
      process.exitCode = 1;
    }
  }
}

main();
