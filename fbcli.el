;;; fbcli.el --- Emacs helpers for fbcli

;; Copyright (C) 2018 Lorenzo Bolla
;; Author: Lorenzo Bolla <lbolla@gmail.com>
;; URL: https://github.com/lbolla/fbcli
;; Created: 20th May 2018
;; Version: 1.0
;; Keywords: fogbugz
;; Package: fbcli

;; This file is free software: you can redistribute it and/or modify
;; it under the terms of the GNU General Public License as published
;; by the Free Software Foundation, either version 3 of the License,
;; or (at your option) any later version.

;; This file is distributed in the hope that it will be useful, but
;; WITHOUT ANY WARRANTY; without even the implied warranty of
;; MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
;; General Public License for more details.

;; You should have received a copy of the GNU General Public License
;; along with this file.  If not, see <http://www.gnu.org/licenses/>.

;;; Commentary:

;; Helpers to deal with fbcli.

;;; Code:

;; List of strings
(defvar fogbugz-constants
  '())

;; List of strings
(defvar fogbugz-keywords
  '())
  
(defvar fogbugz-font-lock-defaults
    `((
       ;; stuff between double quotes
       ("\"\\.\\*\\?" . font-lock-string-face)
       ;; ; : , ; { } =>  @ $ = are all special elements
       (":\\|,\\|;\\|{\\|}\\|=>\\|@\\|$\\|=" . font-lock-keyword-face)
       ( ,(regexp-opt fogbugz-keywords 'words) . font-lock-builtin-face)
       ( ,(regexp-opt fogbugz-constants 'words) . font-lock-constant-face)
       )))

(define-derived-mode fogbugz-mode text-mode
  "FogBugz mode"
  (setq font-lock-defaults fogbugz-font-lock-defaults
        comment-start "#"
        comment-end "")
  (modify-syntax-entry ?# "< b" fogbugz-mode-syntax-table)
  (modify-syntax-entry ?\n "> b" fogbugz-mode-syntax-table))

(add-to-list 'auto-mode-alist '("\\.fbcli_comment\\'" . fogbugz-mode))

(provide 'fbcli)

;;; fbcli.el ends here
