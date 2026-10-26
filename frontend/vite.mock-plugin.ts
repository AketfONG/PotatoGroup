/**
 * 仅开发期使用的 Vite 插件:为前端 mock 模式提供 /__mock_db 读写中间件。
 * - GET  /__mock_db:读取 mock/db.json;不存在则用 mock/db.preset.json 播种
 * - PUT  /__mock_db:把内存中的最新状态写回 mock/db.json(防抖由调用方处理)
 * apply: 'serve' 确保绝不进入生产构建;后端完全不受影响。
 */
import fs from 'node:fs/promises'
import path from 'node:path'
import type { Plugin } from 'vite'

const MOCK_ENDPOINT = '/__mock_db'

export function mockDbPlugin(): Plugin {
  let dbFile = ''
  let presetFile = ''

  return {
    name: 'potato-mock-db',
    apply: 'serve',
    configResolved(config) {
      const root = config.root
      dbFile = path.resolve(root, 'mock/db.json')
      presetFile = path.resolve(root, 'mock/db.preset.json')
    },
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (!req.url?.startsWith(MOCK_ENDPOINT)) {
          next()
          return
        }
        try {
          if (req.method === 'GET') {
            // 首次访问:db.json 不存在时用 preset 播种
            try {
              await fs.access(dbFile)
            } catch {
              const preset = await fs.readFile(presetFile, 'utf-8')
              await fs.mkdir(path.dirname(dbFile), { recursive: true })
              await fs.writeFile(dbFile, preset, 'utf-8')
            }
            const data = await fs.readFile(dbFile, 'utf-8')
            res.statusCode = 200
            res.setHeader('Content-Type', 'application/json')
            res.end(data)
          } else if (req.method === 'PUT') {
            const chunks: Buffer[] = []
            for await (const chunk of req) {
              chunks.push(chunk as Buffer)
            }
            const body = Buffer.concat(chunks).toString('utf-8')
            JSON.parse(body) // 校验合法 JSON,防止写坏文件
            await fs.writeFile(dbFile, body, 'utf-8')
            res.statusCode = 204
            res.end()
          } else {
            res.statusCode = 405
            res.end()
          }
        } catch (err) {
          server.config.logger.error(`[mock-db] ${String(err)}`)
          res.statusCode = 500
          res.end()
        }
      })
    },
  }
}
