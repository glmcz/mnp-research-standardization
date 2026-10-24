# Jin et al. 2025 (global inland waters, figshare 10.6084/m9.figshare.28784873) keep their data as
# R workspaces that no Python reader opens: fitted caret models, each holding the table it was
# trained on. This writes every such table, and any plain data frame, to CSV, unchanged.
#
#   Rscript --vanilla tool/survey/export_jin.R
#   # data/raw/datasets_user/inland/csv/<workspace>__<object>.csv

src <- "data/raw/datasets_user/inland/Data&Rcode_Jin_et_al2025"
out <- "data/raw/datasets_user/inland/csv"
dir.create(out, showWarnings = FALSE, recursive = TRUE)
for (f in list.files(src, pattern = "\\.Rdata$", full.names = TRUE)) {
  env <- new.env()
  names_in <- load(f, envir = env)  # restores objects; runs no code from the file
  for (n in names_in) {
    x <- get(n, envir = env)
    # a fitted caret model keeps the table it was trained on
    if (inherits(x, "train") && is.data.frame(x$trainingData)) x <- x$trainingData
    cat(basename(f), n, class(x)[1], if (is.data.frame(x)) paste(dim(x), collapse = " x ") else "", "\n")
    if (is.data.frame(x)) {
      write.csv(x, file.path(out, paste0(sub("\\.Rdata$", "", basename(f)), "__", n, ".csv")),
                row.names = FALSE)
    }
  }
}
