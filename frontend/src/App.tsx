import { BrowserRouter, Route, Routes } from "react-router-dom"
import { AuthProvider, RequireAuth } from "./components/Auth"
import { ToastProvider } from "./components/Toast"
import AccountPage from "./pages/AccountPage"
import InboxPage from "./pages/InboxPage"
import LoginPage from "./pages/LoginPage"

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<RequireAuth />}>
              <Route path="/" element={<InboxPage />} />
              <Route path="/accounts/:id" element={<AccountPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  )
}
