import { StrictMode, Component, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { WebWorkspace } from './Workspace'
import './web.css'

class WorkspaceBoundary extends Component<{children:ReactNode}, {error:boolean}> {
  state={error:false}
  static getDerivedStateFromError(){return {error:true}}
  render(){return this.state.error?<main className="al-fatal"><h1>页面暂时无法显示</h1><p>工作区记录没有被清空。请刷新页面；仍有问题时保留浏览器存档并查看开发者控制台。</p><button onClick={()=>location.reload()}>重新加载网页</button></main>:this.props.children}
}
createRoot(document.getElementById('root')!).render(<StrictMode><WorkspaceBoundary><WebWorkspace/></WorkspaceBoundary></StrictMode>)
